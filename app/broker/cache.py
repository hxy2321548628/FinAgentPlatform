"""写操作的去重表：同一次工具调用重放时，返回上一次的结果而不再进沙箱。

**要防的是崩溃路径的重复执行。** 崩溃发生在工具执行途中时，那个图节点还没有
pending write，恢复时会整个重跑 —— 于是 `edit_file` 的 `old_string` 已经不在了、
`delete` 的文件已经没了，两者都会返回一个**首次执行时没有的错误**，使 LLM 的后续
行为偏离。因此**错误结果也要缓存**：只缓存成功结果等于没解决这个问题。

**去重放在 broker 而不是 worker**：broker 是沙箱的唯一入口，而 worker 可能有多个
副本、也会崩溃重启 —— 去重状态放在 worker 侧起不到跨副本、跨重启的作用。

**去重键是 `(thread_id, checkpoint_ns)`。** `checkpoint_ns` 实测按**工具调用**唯一
（LangGraph 把每轮的每个工具调用扇出成独立 task），且崩溃重放前后一致。

> **这个键是框架的编排细节，不是本平台的领域概念。** 若 LangGraph 改变扇出粒度
> （比如把同一轮的多个调用合成一个 task），同一轮里的两次调用就会撞键 ——
> 而它坏掉的方式是**静默的**：第二次调用直接拿到第一次的结果。
> 升级 langgraph 时必须重跑 `test/broker/cache_test.py` 里那条并行场景的用例。
"""

import json
import logging

from redis.asyncio import Redis
from redis.exceptions import RedisError

from store.redis import check

logger = logging.getLogger(__name__)

KEY_PREFIX = "zuel:tool:"

# 缓存留多久。崩溃恢复只要几分钟就够，但审批可以挂 24 小时 ——
# 取一个盖得住最长挂起时长的数，一条记录也就几百字节
DEFAULT_TTL_SECOND = 48 * 60 * 60

# 单条结果的大小上限。`execute` 的输出在沙箱那一侧已经截断过，正常远低于这个数；
# 真撞上就**不缓存并告警**，而不是截断后缓存 —— 截断过的结果与首次执行不一致，
# 那比不去重更糟
DEFAULT_MAX_BYTE = 256 * 1024


class ToolCache:
    """按 `(thread_id, checkpoint_ns)` 记住一次写操作的结果。

    Args:
        client: Redis 客户端。
        ttl_second: 一条记录留多久。
        max_byte: 单条结果的大小上限，超了就不缓存。
    """

    def __init__(
        self,
        client: Redis,
        *,
        ttl_second: int = DEFAULT_TTL_SECOND,
        max_byte: int = DEFAULT_MAX_BYTE,
    ) -> None:
        self._client = client
        self._ttl = ttl_second
        self._max_byte = max_byte

    async def check(self) -> None:
        """确认去重表连得上，连不上就抛。

        Raises:
            RedisUnavailableError: 连接不上。
        """
        await check(self._client)

    async def get(self, thread_id: str, checkpoint_ns: str) -> dict[str, object] | None:
        """取这次调用上一次的结果。

        Args:
            thread_id: 会话标识。
            checkpoint_ns: LangGraph 给这次工具调用的命名空间。

        Returns:
            缓存的结果；没记过则 None。
        """
        try:
            found = await self._client.get(_key(thread_id, checkpoint_ns))
        # **去重表连不上时降级，不把这次工具调用打断。** 它是崩溃路径上的一道保险，
        # 而不是执行的前提 —— 为了保险失灵就让每一次写操作都 500，代价大得多。
        # 但必须吼出来：这段时间里重放是会真的重跑的
        except RedisError:
            logger.warning("去重表读不到，这一次不去重：thread_id=%s", thread_id, exc_info=True)
            return None
        if found is None:
            return None
        parsed: dict[str, object] = json.loads(found)
        return parsed

    async def put(self, thread_id: str, checkpoint_ns: str, result: dict[str, object]) -> None:
        """记下这次调用的结果。**成功与失败一视同仁。**

        Args:
            thread_id: 会话标识。
            checkpoint_ns: LangGraph 给这次工具调用的命名空间。
            result: 工具的返回，原样存。
        """
        payload = json.dumps(result, ensure_ascii=False)
        if len(payload.encode()) > self._max_byte:
            logger.warning(
                "工具结果太大，这一次不去重：thread_id=%s checkpoint_ns=%s size=%d",
                thread_id,
                checkpoint_ns,
                len(payload),
            )
            return
        try:
            await self._client.set(_key(thread_id, checkpoint_ns), payload, ex=self._ttl)
        # 同上：记不下只意味着这一次调用没有保险，不该让工具调用失败
        except RedisError:
            logger.warning("去重表写不进，这一次不去重：thread_id=%s", thread_id, exc_info=True)


def _key(thread_id: str, checkpoint_ns: str) -> str:
    return f"{KEY_PREFIX}{thread_id}:{checkpoint_ns}"
