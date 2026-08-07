"""任务队列：一条 Redis Stream 加一个 consumer group。

**至少一次投递。** 领走的消息进 pending 列表，跑完才 `XACK`；worker 崩了消息还在
pending 里，另一个 worker 用 `XAUTOCLAIM` 认领过去接着跑。重复执行因此是可能的 ——
那不是 bug，是至少一次投递的定义。

**ack 的时机是这段代码最容易写错的地方。** 收到就 ack 等于放弃重投，崩溃即丢；
跑完才 ack 则一次几十分钟的任务会一直占着 pending —— 后者是对的，但它带来一个新问题：
认领的判据是「消息多久没被碰过」，而一个健康的 worker 跑四十分钟也一样是「没碰过」。
`touch` 就是为此存在的：跑着的 worker 定期把自己那条消息的 idle 归零，
认领阈值因此可以设得很短，崩溃恢复不必等上几十分钟。
"""

import logging
from typing import cast

from pydantic import BaseModel, Field
from redis.asyncio import Redis
from redis.exceptions import ResponseError

from store.redis import StreamEntry

logger = logging.getLogger(__name__)

TASK_STREAM = "zuel:task:run"
CONSUMER_GROUP = "zuel:worker"

# Stream 的每条 entry 只有一个字段，装整条任务的 JSON
PAYLOAD_FIELD = "data"

# 已经 ack 的消息不会自动从 Stream 里消失，只是出了 pending 列表。
# 没有这条上限，Stream 会随历史 run 无限长大
DEFAULT_MAX_LENGTH = 10_000

# 领任务时阻塞多久。**不是轮询间隔** —— 有任务立刻返回，
# 这个数只决定 worker 多久回一次主循环去看「该停了没」
DEFAULT_BLOCK_MILLISECOND = 5_000

# 一条消息多久没被碰过就允许别的 worker 认领。跑着的 worker 会定期 touch，
# 因此这个数只需要「明显大于一次 touch 的间隔」，而不必大于一次 run 的时长
DEFAULT_CLAIM_IDLE_MILLISECOND = 60_000

# 从 pending 列表的最前面开始扫
CLAIM_START = "0-0"

# XREADGROUP 的特殊 id：只要还没分给任何人的新消息
NEW_MESSAGE = ">"

# XGROUP CREATE 撞上已存在的 group 时 Redis 回这个前缀
GROUP_EXISTS = "BUSYGROUP"


class RunTask(BaseModel):
    """一次待执行的分析。

    **worker 要的字段一次给全**：少一个它就得回头查库，而那正是拆进程之后
    最容易被忽略的一次额外往返。
    """

    run_id: str = Field(min_length=1, description="run 标识，事件与元数据都按它归集")
    thread_id: str = Field(min_length=1, description="所属会话，沙箱与文件空间按它隔离")
    content: str = Field(min_length=1, description="教师的问题")
    # worker 不拿它做任何判断（授权在提交那一刻就做完了），只把它带进日志 ——
    # 少了它，「这个用户今天的执行日志」在 worker 那一侧一条都过滤不出来
    user_id: str | None = Field(default=None, description="提交的人，只用于日志归集")


class Delivery(BaseModel):
    """一条领到手的任务，连同它在队列里的编号。

    编号是 ack 与 touch 的凭据，与 `RunTask` 分开是因为它属于传输层，不属于任务本身。
    """

    id: str = Field(min_length=1, description="Stream 里的消息 id")
    task: RunTask = Field(description="任务本身")


class TaskQueue:
    """按 consumer group 分发任务的队列。

    Args:
        client: Redis 客户端。
        consumer: 本进程在 group 里的名字，崩溃后按它认领。
        max_length: Stream 保留的消息条数上限。
        block_millisecond: 领任务时单次阻塞的时长。
        claim_idle_millisecond: 消息闲置多久后允许被别的 worker 认领。
    """

    def __init__(
        self,
        client: Redis,
        *,
        consumer: str,
        max_length: int = DEFAULT_MAX_LENGTH,
        block_millisecond: int = DEFAULT_BLOCK_MILLISECOND,
        claim_idle_millisecond: int = DEFAULT_CLAIM_IDLE_MILLISECOND,
    ) -> None:
        self._client = client
        self._consumer = consumer
        self._max_length = max_length
        self._block = block_millisecond
        self._claim_idle = claim_idle_millisecond
        # 已经领到手、还没 ack 的消息。**认领时要跳过它们** —— XAUTOCLAIM 不区分
        # 消息现在归谁，本进程正在跑的那条同样会被自己重新认领一次，
        # 于是同一个 run 在同一个进程里跑了两遍
        self._held: set[str] = set()

    async def ensure_group(self) -> None:
        """建好 consumer group，已经有了就当无事发生。

        **每个 worker 启动时都调一次**：谁先起来谁建，不必有一个「负责初始化」的角色。
        """
        try:
            await self._client.xgroup_create(TASK_STREAM, CONSUMER_GROUP, id="0", mkstream=True)
        except ResponseError as exc:
            if GROUP_EXISTS not in str(exc):
                raise
            logger.debug("consumer group 已存在，跳过创建")

    async def publish(self, task: RunTask) -> str:
        """把一次分析投进队列。

        Args:
            task: 待执行的分析。

        Returns:
            消息 id。
        """
        assigned = await self._client.xadd(
            TASK_STREAM,
            {PAYLOAD_FIELD: task.model_dump_json()},
            maxlen=self._max_length,
            approximate=True,
        )
        return cast(str, assigned)

    async def reserve(self) -> Delivery | None:
        """领一条任务。没有可领的就阻塞一段时间后返回 None。

        **先认领超时的，再取新的**：崩溃遗留的任务比新任务更该先跑完 ——
        它已经烧过一轮 token，让它继续排在新任务后面就是把那笔钱再花一次。

        Returns:
            领到的任务；这一轮没有则 None。
        """
        reclaimed = await self._claim()
        if reclaimed is not None:
            logger.info("认领了一条超时未完成的任务：message_id=%s run_id=%s", reclaimed.id, reclaimed.task.run_id)
            return reclaimed

        batch = cast(
            list[tuple[str, list[StreamEntry]]],
            await self._client.xreadgroup(
                CONSUMER_GROUP,
                self._consumer,
                {TASK_STREAM: NEW_MESSAGE},
                count=1,
                block=self._block,
            )
            or [],
        )
        for _, entry in batch:
            for message_id, field in entry:
                self._held.add(message_id)
                return _decode(message_id, field)
        return None

    async def ack(self, message_id: str) -> None:
        """确认一条任务已经处理完，把它移出 pending 列表。"""
        await self._client.xack(TASK_STREAM, CONSUMER_GROUP, message_id)
        self._held.discard(message_id)

    async def touch(self, message_id: str) -> None:
        """把一条自己持有的消息的闲置时间归零，宣告「我还活着」。

        不这么做的话，认领阈值就必须大于最长的一次 run，
        而那意味着崩溃恢复要等上几十分钟。
        """
        await self._client.xclaim(
            TASK_STREAM,
            CONSUMER_GROUP,
            self._consumer,
            min_idle_time=0,
            message_ids=[message_id],
            justid=True,
        )

    async def pending_count(self) -> int:
        """还有多少条任务领了但没 ack。

        Returns:
            pending 列表的长度。
        """
        summary = await self._client.xpending(TASK_STREAM, CONSUMER_GROUP)
        count: int = summary["pending"]
        return count

    async def _claim(self) -> Delivery | None:
        """认领一条闲置超时、且不在自己手上的消息。"""
        cursor = CLAIM_START
        while True:
            following, entry, _ = await self._client.xautoclaim(
                TASK_STREAM,
                CONSUMER_GROUP,
                self._consumer,
                min_idle_time=self._claim_idle,
                start_id=cursor,
                count=1,
            )
            if not entry:
                return None
            message_id, field = entry[0]
            if message_id not in self._held:
                self._held.add(message_id)
                return _decode(message_id, field)
            # 扫回起点说明这一圈里剩下的全是自己手上的那些
            if following == CLAIM_START:
                return None
            cursor = following


def _decode(message_id: str, field: dict[str, str]) -> Delivery:
    """把一条 Stream entry 还原成任务。"""
    return Delivery(id=message_id, task=RunTask.model_validate_json(field[PAYLOAD_FIELD]))
