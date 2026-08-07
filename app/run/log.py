"""事件日志：一个 run 产生的事件按顺序存下来，供 SSE 订阅与断线补齐。

**存在 Redis Stream 里，一个 run 一条流。** 追加是 `XADD`，补历史是 `XRANGE`，
跟新事件是 `XREAD BLOCK`。

**对外契约一个字没变**：事件 id 仍是 `{毫秒}-{同毫秒内序号}`，因为 P0 那版内存实现
本来就是照 Redis Stream 的规则自己发号的（这是当时刻意留的接口）。换到真 Stream 之后，
发号的人从进程变成了 Redis，`Last-Event-ID` 的语义、前端的解析全都原样成立。

`XREAD BLOCK` 顶掉了内存版那个用来唤醒 follower 的 `asyncio.Event`：新事件一到
就返回，不靠轮询。超时只是安全网，用来周期性地重新判断「这个 run 是不是已经结束了」。

条数上限由 `MAXLEN` 控。**按时间的保留策略与归档在步骤五**，本步只保证不无界增长。
"""

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import cast

from redis.asyncio import Redis

from event.model import EVENT_ADAPTER, TERMINAL_EVENT_TYPE, Event

logger = logging.getLogger(__name__)

# Stream 里的一条：id 与字段表。客户端建的时候开了 decode_responses，
# 因此实际拿到的都是 str，而 redis-py 的签名把 bytes 与 None 也算在内 ——
# 读命令那几处要 cast 一次，原因就是这个
type StreamEntry = tuple[str, dict[str, str]]

# per-run 的事件条数上限。实测一次完整分析约 300 条，留两个数量级的余量：
# 超出即意味着断线重连可能补不齐，宁可多占内存也不轻易触发。
DEFAULT_MAX_LENGTH = 20_000

# `XREAD` 阻塞多久后回来看一眼。**不是轮询间隔** —— 新事件一到就立刻返回，
# 这个数只决定「run 已经结束但终态事件在游标之前」那种情形多久能收尾
DEFAULT_BLOCK_MILLISECOND = 5_000

KEY_PREFIX = "zuel:event"

# Stream 的每条 entry 只有一个字段，装整条事件的 JSON。拆成多字段没有收益 ——
# 读的时候总是整条取走，而拆开之后每加一个事件字段都要动这里
PAYLOAD_FIELD = "data"

ID_SEPARATOR = "-"

# XRANGE / XREAD 的边界记号
STREAM_START = "-"
STREAM_END = "+"
EXCLUSIVE = "("
FROM_BEGINNING = "0-0"


class InvalidEventIdError(ValueError):
    """事件 id 不合法。

    游标来自客户端的 `Last-Event-ID` 请求头，属于不可信输入 —— 解析不了要明确拒绝，
    不能当成「从头开始」，那会让客户端收到一整份重复的历史。
    """


@dataclass(frozen=True)
class LoggedEvent:
    """事件与它在日志里的位置。

    `id` 由 Redis 在追加时分配，事件本身不带 —— 断线重连认的就是这个号。
    """

    id: str
    event: Event


def stream_key(run_id: str) -> str:
    """一个 run 的事件流在 Redis 里的键名。"""
    return f"{KEY_PREFIX}:{run_id}"


class EventLog:
    """按 run 分流的事件日志。

    Args:
        client: Redis 客户端。
        max_length: 每个 run 保留的事件条数上限。
        block_millisecond: 跟新事件时单次阻塞的时长。
    """

    def __init__(
        self,
        client: Redis,
        *,
        max_length: int = DEFAULT_MAX_LENGTH,
        block_millisecond: int = DEFAULT_BLOCK_MILLISECOND,
    ) -> None:
        self._client = client
        self._max_length = max_length
        self._block = block_millisecond

    async def append(self, event: Event) -> LoggedEvent:
        """追加一个事件并拿到 Redis 分配的 id。

        Args:
            event: 待追加的事件，所属 run 取自它的 `run_id`。

        Returns:
            带 id 的事件。
        """
        key = stream_key(event.run_id)
        async with self._client.pipeline(transaction=True) as pipe:
            # 精确裁剪而不是 `~` 近似：近似模式下实际条数会飘到上限之上，
            # 「保留最近 N 条」这个承诺就变成了「大约 N 条」
            pipe.xadd(key, {PAYLOAD_FIELD: event.model_dump_json()}, maxlen=self._max_length, approximate=False)
            pipe.xlen(key)
            assigned, length = await pipe.execute()

        if length >= self._max_length:
            logger.warning(
                "事件日志已达上限，最早的事件被丢弃，断线重连可能补不齐：run_id=%s max_length=%d",
                event.run_id,
                self._max_length,
            )
        identifier: str = assigned
        return LoggedEvent(id=identifier, event=event)

    async def read(self, run_id: str, *, after: str | None = None) -> list[LoggedEvent]:
        """读取一个 run 的事件。

        Args:
            run_id: 目标 run。
            after: 只返回该 id 之后的事件；不传则返回全部。

        Returns:
            按发生顺序排列的事件，run 不存在时为空。

        Raises:
            InvalidEventIdError: `after` 不是合法的事件 id。
        """
        start = STREAM_START if after is None else f"{EXCLUSIVE}{_validate(after)}"
        entry = cast(list[StreamEntry], await self._client.xrange(stream_key(run_id), min=start, max=STREAM_END))
        return [_decode(one) for one in entry]

    async def follow(self, run_id: str, *, after: str | None = None) -> AsyncIterator[LoggedEvent]:
        """先补齐历史，再持续产出新事件，直到 run 进入终态。

        Args:
            run_id: 目标 run。
            after: 从该 id 之后接着读；不传则从头。

        Yields:
            按发生顺序排列的事件。

        Raises:
            InvalidEventIdError: `after` 不是合法的事件 id。
        """
        cursor = FROM_BEGINNING if after is None else _validate(after)
        key = stream_key(run_id)
        while True:
            # 先判「已经结束且游标在末尾」再阻塞：跑完之后才来订阅的连接不该白等一轮，
            # 而这个 run 再也不会有新事件了
            if await self._ended(run_id, cursor):
                return
            # XREAD 取的是游标之后的 entry，因此「读完到开始等待之间新来的事件」
            # 不会漏 —— 内存实现里要靠一个 asyncio.Event 才能避免的那个竞态，这里不存在
            batch = cast(
                list[tuple[str, list[StreamEntry]]],
                await self._client.xread({key: cursor}, block=self._block) or [],
            )
            for _, entry in batch:
                for one in entry:
                    logged = _decode(one)
                    cursor = logged.id
                    yield logged
                    if logged.event.type in TERMINAL_EVENT_TYPE:
                        return

    async def _ended(self, run_id: str, cursor: str) -> bool:
        """这个 run 是否已经结束，且游标已经走过了终态事件。

        只看流里最后一条：终态事件是一个 run 最后发的东西，它之后不该再有别的。
        """
        last = cast(
            list[StreamEntry],
            await self._client.xrevrange(stream_key(run_id), max=STREAM_END, min=STREAM_START, count=1),
        )
        if not last:
            return False
        logged = _decode(last[0])
        if parse_event_id(logged.id) > parse_event_id(cursor):
            return False
        return logged.event.type in TERMINAL_EVENT_TYPE


def _decode(entry: StreamEntry) -> LoggedEvent:
    """把一条 Stream entry 还原成事件。"""
    entry_id, field = entry
    return LoggedEvent(id=entry_id, event=EVENT_ADAPTER.validate_json(field[PAYLOAD_FIELD]))


def _validate(event_id: str) -> str:
    """确认游标能被 Redis 当成 id 用，不合法就拒绝。"""
    parse_event_id(event_id)
    return event_id


def parse_event_id(event_id: str) -> tuple[int, int]:
    """把事件 id 拆成可比较的二元组。

    直接比字符串是错的：`"10-0" < "9-0"` 成立，会把整段历史当成未读重发。

    Args:
        event_id: 形如 `1753948800123-0` 的事件 id。

    Returns:
        (毫秒, 同毫秒内序号)。

    Raises:
        InvalidEventIdError: 格式不合法。
    """
    millisecond, separator, sequence = event_id.partition(ID_SEPARATOR)
    if not separator or not millisecond.isdigit() or not sequence.isdigit():
        message = f"事件 id 格式不合法：{event_id!r}"
        raise InvalidEventIdError(message)
    return int(millisecond), int(sequence)
