"""跨队列传递 trace 上下文。

**整条链路上唯一要手接的一段。** HTTP 那几跳由 httpx 与 FastAPI 的探针自动完成 ——
traceparent 放进请求头、对面取出来，全程不用写一行代码。而 api 与 worker 之间隔着
一条 Redis Stream，没有请求头这回事：不把上下文原样塞进任务消息里带过去，
每个 run 就断成互不相干的两条 trace，而**「一个 run 的完整耗时」正好落在断口上**。

用的是 W3C `traceparent` 那套标准编码，不是自己发明的字段 —— 换掉任何一端的实现
都不必改这里。
"""

from opentelemetry.context import Context
from opentelemetry.propagate import extract, inject


def carry() -> dict[str, str]:
    """把当前的 trace 上下文装成一个可以随消息走的小字典。

    Returns:
        W3C 的 `traceparent`（有时还有 `tracestate`）。没有在跑的 trace 时是空字典。
    """
    carrier: dict[str, str] = {}
    inject(carrier)
    return carrier


def resume(carrier: dict[str, str] | None) -> Context | None:
    """从消息里带来的字典恢复出上下文，用作新 span 的父。

    Args:
        carrier: `carry()` 的产物。**允许为 None** —— 这个字段是 P4 才加的，
            队列里躺着的旧消息没有它，那时就当一条新 trace 开头，而不是报错。

    Returns:
        可以传给 `start_span(context=...)` 的上下文；没得恢复时 None。
    """
    if not carrier:
        return None
    return extract(carrier)
