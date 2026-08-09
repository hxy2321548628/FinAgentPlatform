"""事件到 SSE 报文的序列化。

`id:` 那一行是断线重连的全部依据 —— 浏览器会把最后收到的 id 记下来，
重连时放进 `Last-Event-ID` 请求头，服务端据此补齐中间的事件。少写这一行，
重连就只能从头开始或者干脆漏事件。
"""

from run.log import LoggedEvent

# SSE 用空行分隔报文，缺了它这一条永远不会被客户端派发
FRAME_END = "\n\n"


def format_event(logged: LoggedEvent) -> str:
    """把一个事件序列化成一条 SSE 报文。

    Args:
        logged: 带 id 的事件。

    Returns:
        可直接写进响应体的报文。
    """
    payload = logged.event.model_dump_json()
    return f"id: {logged.id}\nevent: {logged.event.type.value}\ndata: {payload}{FRAME_END}"
