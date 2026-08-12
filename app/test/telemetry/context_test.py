"""跨队列传上下文：整条链路上唯一要手接的一段。

**这一段断掉不会报错**，只会让每个 run 变成两条互不相干的 trace ——
而验收 ① 要的「一个 run 的完整耗时」恰好落在断口上。因此这里断的是
「worker 侧那个 span 的 trace_id 与 api 侧的是同一个」，不是「字段非空」。
"""

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from telemetry.context import carry, resume

TRACEPARENT = "traceparent"


def a_provider() -> tuple[TracerProvider, InMemorySpanExporter]:
    """一套只往内存里写的 SDK。

    **不碰全局 provider** —— 那是模块级可变状态，用例之间会互相污染，
    且第二次设置会被 OTel 直接忽略。
    """
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider, exporter


def test_a_running_trace_is_carried_as_a_traceparent() -> None:
    provider, _ = a_provider()
    tracer = provider.get_tracer(__name__)

    with tracer.start_as_current_span("api"):
        carrier = carry()

    assert TRACEPARENT in carrier


def test_nothing_is_carried_when_no_trace_is_running() -> None:
    """没有在跑的 trace 时给空字典，而不是一个指向「无效 span」的 traceparent。"""
    assert carry() == {}


def test_the_worker_side_span_lands_in_the_same_trace() -> None:
    """**这一条就是整个模块存在的理由。**

    两侧各开一个 span，中间只靠一个字典传过去；断言两者的 trace_id 相同 ——
    「字段非空」证明不了它们串上了，只有 trace_id 能。
    """
    provider, exporter = a_provider()
    tracer = provider.get_tracer(__name__)

    with tracer.start_as_current_span("api.submit") as submitted:
        carrier = carry()
        expected = submitted.get_span_context().trace_id

    with tracer.start_as_current_span("run.execute", context=resume(carrier)) as executed:
        assert executed.get_span_context().trace_id == expected

    assert {one.name for one in exporter.get_finished_spans()} == {"api.submit", "run.execute"}


def test_an_old_message_without_the_field_starts_its_own_trace() -> None:
    """`trace` 字段是 P4 才加的，队列里躺着的旧消息没有它。

    那时该当一条新 trace 开头 —— 报错的话，升级那一刻队列里的存货会全部执行失败。
    """
    assert resume(None) is None
    assert resume({}) is None
