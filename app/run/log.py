"""事件日志：一个 run 产生的事件按顺序存下来，供 SSE 订阅与断线补齐。

**接口照 Redis Stream 的形状设计**（追加时发号、按 id 之后范围读、per-run 有上限），
本期是内存实现，换成 Redis 时只改这个类，不动调用方。这是本期唯一一处提前投入的抽象 ——
换掉它的时机是确定的（进程重启即丢事件，这笔债已登记），而调用方遍布执行器与 SSE 端点。

内存实现比 Redis 多欠两件事：进程重启事件全丢，以及事件只保留最近若干条 ——
被裁掉的那段无法补齐，因此裁剪时会记警告。
"""

import asyncio
import logging
import time
from collections import OrderedDict, deque
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from event.model import TERMINAL_EVENT_TYPE, Event

logger = logging.getLogger(__name__)

# per-run 的事件条数上限。实测一次完整分析约 300 条，留两个数量级的余量：
# 超出即意味着断线重连可能补不齐，宁可多占内存也不轻易触发。
DEFAULT_MAX_LENGTH = 20_000

# 同时保留多少个 run 的事件。进程长跑时 run 只增不减，没有这条会无界增长；
# 超出后按最早追加的 run 整个丢弃。
DEFAULT_MAX_RUN = 200

ID_SEPARATOR = "-"


class InvalidEventIdError(ValueError):
    """事件 id 不合法。

    游标来自客户端的 `Last-Event-ID` 请求头，属于不可信输入 —— 解析不了要明确拒绝，
    不能当成「从头开始」，那会让客户端收到一整份重复的历史。
    """


@dataclass(frozen=True)
class LoggedEvent:
    """事件与它在日志里的位置。

    `id` 由日志在追加时分配，事件本身不带 —— 断线重连认的就是这个号。
    """

    id: str
    event: Event


@dataclass
class _Stream:
    """一个 run 的事件序列与它的发号状态。"""

    entry: deque[LoggedEvent]
    last_millisecond: int = 0
    last_sequence: int = 0
    # 追加时唤醒所有在等新事件的 follower。没人在等时它也存在，代价是一个空对象。
    arrival: asyncio.Event = field(default_factory=asyncio.Event)


class EventLog:
    """按 run 分流的事件日志。

    Args:
        max_length: 每个 run 保留的事件条数上限。
        max_run: 同时保留的 run 数上限，超出后丢弃最早的 run。
    """

    def __init__(self, *, max_length: int = DEFAULT_MAX_LENGTH, max_run: int = DEFAULT_MAX_RUN) -> None:
        self._max_length = max_length
        self._max_run = max_run
        self._stream: OrderedDict[str, _Stream] = OrderedDict()

    def append(self, event: Event) -> LoggedEvent:
        """追加一个事件并分配 id。

        Args:
            event: 待追加的事件，所属 run 取自它的 `run_id`。

        Returns:
            带 id 的事件。
        """
        stream = self._stream_for(event.run_id)
        logged = LoggedEvent(id=self._next_id(stream), event=event)

        if len(stream.entry) == self._max_length:
            logger.warning(
                "事件日志已达上限，最早的事件被丢弃，断线重连可能补不齐：run_id=%s max_length=%d",
                event.run_id,
                self._max_length,
            )
        stream.entry.append(logged)

        stream.arrival.set()
        stream.arrival = asyncio.Event()
        return logged

    def read(self, run_id: str, *, after: str | None = None) -> list[LoggedEvent]:
        """读取一个 run 的事件。

        Args:
            run_id: 目标 run。
            after: 只返回该 id 之后的事件；不传则返回全部。

        Returns:
            按发生顺序排列的事件，run 不存在时为空。

        Raises:
            InvalidEventIdError: `after` 不是合法的事件 id。
        """
        cursor = None if after is None else parse_event_id(after)
        stream = self._stream.get(run_id)
        if stream is None:
            return []
        if cursor is None:
            return list(stream.entry)
        return [logged for logged in stream.entry if parse_event_id(logged.id) > cursor]

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
        cursor = after
        while True:
            # 必须先取 waiter 再读：反过来的话，读完到开始等待之间追加的事件
            # 会唤醒一个已经被换掉的 waiter，这一轮就白等了。
            arrival = self._stream_for(run_id).arrival
            pending = self.read(run_id, after=cursor)
            if not pending:
                await arrival.wait()
                continue
            for logged in pending:
                cursor = logged.id
                yield logged
                if logged.event.type in TERMINAL_EVENT_TYPE:
                    return

    def _stream_for(self, run_id: str) -> _Stream:
        stream = self._stream.get(run_id)
        if stream is not None:
            return stream

        stream = _Stream(entry=deque(maxlen=self._max_length))
        self._stream[run_id] = stream
        while len(self._stream) > self._max_run:
            evicted, _ = self._stream.popitem(last=False)
            logger.warning("事件日志的 run 数已达上限，整个 run 的事件被丢弃：run_id=%s", evicted)
        return stream

    def _next_id(self, stream: _Stream) -> str:
        """按 Redis Stream 的规则发号：毫秒时间戳 + 同毫秒内递增的序号。"""
        millisecond = time.time_ns() // 1_000_000
        if millisecond > stream.last_millisecond:
            stream.last_millisecond = millisecond
            stream.last_sequence = 0
        else:
            stream.last_sequence += 1
        return f"{stream.last_millisecond}{ID_SEPARATOR}{stream.last_sequence}"


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
