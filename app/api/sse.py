"""事件到 SSE 报文的序列化，以及静默期的心跳。

`id:` 那一行是断线重连的全部依据 —— 浏览器会把最后收到的 id 记下来，
重连时放进 `Last-Event-ID` 请求头，服务端据此补齐中间的事件。少写这一行，
重连就只能从头开始或者干脆漏事件。
"""

import asyncio
from collections.abc import AsyncIterator

from run.log import LoggedEvent

# SSE 用空行分隔报文，缺了它这一条永远不会被客户端派发
FRAME_END = "\n\n"

# 心跳走 SSE 注释行（冒号开头）。**不能给它 id** —— 客户端会把 id 记成
# Last-Event-ID，重连时就从心跳之后开始读，中间的真事件全被跳过。
HEARTBEAT_FRAME = f":heartbeat{FRAME_END}"

# 静默多久发一次心跳。要远小于反代的 proxy_read_timeout（默认 60s），
# 也要小于常见浏览器与中间代理的空闲上限。
DEFAULT_HEARTBEAT_INTERVAL = 15.0


def format_event(logged: LoggedEvent) -> str:
    """把一个事件序列化成一条 SSE 报文。

    Args:
        logged: 带 id 的事件。

    Returns:
        可直接写进响应体的报文。
    """
    payload = logged.event.model_dump_json()
    return f"id: {logged.id}\nevent: {logged.event.type.value}\ndata: {payload}{FRAME_END}"


async def _next(iterator: AsyncIterator[LoggedEvent]) -> LoggedEvent:
    """取下一个事件。包一层是为了拿到一个能交给 create_task 的协程。"""
    return await anext(iterator)


async def heartbeat_stream(
    source: AsyncIterator[LoggedEvent],
    *,
    interval: float = DEFAULT_HEARTBEAT_INTERVAL,
) -> AsyncIterator[str]:
    """把事件流序列化成 SSE 报文，并在静默期插入心跳。

    **心跳是上反代的硬前提，不是附加项**：排队等沙箱那几分钟一个字节都不会产生，
    而 Nginx 默认 `proxy_read_timeout` 是 60 秒，会先把连接掐掉。

    等待用的是同一个待办任务而不是每轮新建一个：`anext` 在同一个生成器上并发调用
    两次会直接抛 RuntimeError，超时之后必须接着等原来那个。

    Args:
        source: 事件来源，通常是事件日志的 `follow`。
        interval: 静默多久发一次心跳，秒。

    Yields:
        可直接写进响应体的 SSE 报文。
    """
    iterator = source.__aiter__()
    pending: asyncio.Task[LoggedEvent] | None = None
    try:
        while True:
            if pending is None:
                pending = asyncio.create_task(_next(iterator))
            done, _ = await asyncio.wait({pending}, timeout=interval)
            if not done:
                yield HEARTBEAT_FRAME
                continue

            arrived, pending = pending, None
            try:
                logged = arrived.result()
            except StopAsyncIteration:
                return
            yield format_event(logged)
    finally:
        # 对端断开时生成器会被关掉，挂着的等待要跟着撤销，否则它会一直挂在事件日志上
        if pending is not None:
            pending.cancel()
