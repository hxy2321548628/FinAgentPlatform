"""run 那一段 span 上的属性。

**验收 ①「给一个 run_id，拿到它各段的耗时与这次的 token」全靠这些属性。**
Tempo 按属性检索：`zuel.run_id` 缺了，「按 run_id 找那条 trace」就无从谈起 ——
只剩按时间范围翻，而那与「日志里都有，自己 grep」是同一件事。
"""

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from event.model import (
    RunCancelledData,
    RunCancelledEvent,
    RunFailedData,
    RunFailedEvent,
    RunFinishedData,
    RunFinishedEvent,
    RunStartedData,
    RunStartedEvent,
    TokenUsage,
)
from telemetry.run import (
    CACHE_READ_ATTRIBUTE,
    OUTPUT_ATTRIBUTE,
    RESUMED_ATTRIBUTE,
    RUN_ATTRIBUTE,
    SPAN_NAME,
    STATUS_ATTRIBUTE,
    THREAD_ATTRIBUTE,
    UNCACHED_ATTRIBUTE,
    USER_ATTRIBUTE,
    execution,
    mark_resumed,
    record,
)

RUN = "run-1"
THREAD = "thread-1"
USER = "user-1"

# 三个数互不相同：属性写串了才看得出来
TOKENS = TokenUsage(input_cache_read=11, input_uncached=22, output=33)


def only(exporter: InMemorySpanExporter) -> ReadableSpan:
    found = [one for one in exporter.get_finished_spans() if one.name == SPAN_NAME]
    assert len(found) == 1, f"应当只有一个 {SPAN_NAME}，实际 {[one.name for one in exporter.get_finished_spans()]}"
    return found[0]


def attribute(span: ReadableSpan, name: str) -> object:
    return dict(span.attributes or {}).get(name)


def a_finished(tokens: TokenUsage = TOKENS) -> RunFinishedEvent:
    return RunFinishedEvent(ts=1, run_id=RUN, path=(), data=RunFinishedData(tokens=tokens))


def test_the_run_id_is_on_the_span(recorded_span: InMemorySpanExporter) -> None:
    """没有它就没法按 run_id 检索，而那正是验收 ① 的第一句话。"""
    with execution(run_id=RUN, thread_id=THREAD, user_id=USER, carrier=None):
        pass

    span = only(recorded_span)
    assert attribute(span, RUN_ATTRIBUTE) == RUN
    assert attribute(span, THREAD_ATTRIBUTE) == THREAD
    assert attribute(span, USER_ATTRIBUTE) == USER


def test_an_unowned_task_leaves_the_user_attribute_out(recorded_span: InMemorySpanExporter) -> None:
    """归属未知时不写这个属性，而不是写一个空串 —— 空串会在检索里变成一个真实的值。"""
    with execution(run_id=RUN, thread_id=THREAD, user_id=None, carrier=None):
        pass

    assert attribute(only(recorded_span), USER_ATTRIBUTE) is None


def test_the_token_triple_lands_on_the_span(recorded_span: InMemorySpanExporter) -> None:
    """验收 ① 的后半句：「以及这次的 token 三元组」。"""
    with execution(run_id=RUN, thread_id=THREAD, user_id=USER, carrier=None):
        record(a_finished())

    span = only(recorded_span)
    assert attribute(span, CACHE_READ_ATTRIBUTE) == TOKENS.input_cache_read
    assert attribute(span, UNCACHED_ATTRIBUTE) == TOKENS.input_uncached
    assert attribute(span, OUTPUT_ATTRIBUTE) == TOKENS.output
    assert attribute(span, STATUS_ATTRIBUTE) == "run.finished"


def test_a_cancelled_run_still_reports_what_it_burned(recorded_span: InMemorySpanExporter) -> None:
    """取消不是失败，而「这次白花了多少」正是下一个要问的问题。"""
    with execution(run_id=RUN, thread_id=THREAD, user_id=USER, carrier=None):
        record(RunCancelledEvent(ts=1, run_id=RUN, path=(), data=RunCancelledData(tokens=TOKENS)))

    span = only(recorded_span)
    assert attribute(span, STATUS_ATTRIBUTE) == "run.cancelled"
    assert attribute(span, UNCACHED_ATTRIBUTE) == TOKENS.input_uncached


def test_a_failed_run_has_a_status_but_no_token(recorded_span: InMemorySpanExporter) -> None:
    """失败的 run 有状态但没有用量。

    `run.failed` 的载荷里只有原因 —— 编一个 0 会让「没花钱」与「不知道花了多少」
    在看板上分不开。
    """
    with execution(run_id=RUN, thread_id=THREAD, user_id=USER, carrier=None):
        record(
            RunFailedEvent(
                ts=1, run_id=RUN, path=(), data=RunFailedData(code="INTERNAL", message="炸了", retryable=True)
            )
        )

    span = only(recorded_span)
    assert attribute(span, STATUS_ATTRIBUTE) == "run.failed"
    assert attribute(span, UNCACHED_ATTRIBUTE) is None


def test_a_non_terminal_event_leaves_no_conclusion(recorded_span: InMemorySpanExporter) -> None:
    """`_emit` 是所有事件的漏斗，一次 run 会经过它几十次。只有终态才该留下结论。"""
    with execution(run_id=RUN, thread_id=THREAD, user_id=USER, carrier=None):
        record(RunStartedEvent(ts=1, run_id=RUN, path=(), data=RunStartedData(thread_id=THREAD, resumed=False)))

    assert attribute(only(recorded_span), STATUS_ATTRIBUTE) is None


def test_the_resumed_flag_is_recorded(recorded_span: InMemorySpanExporter) -> None:
    """崩溃恢复与审批续跑那几程要能在 trace 上一眼认出来。"""
    with execution(run_id=RUN, thread_id=THREAD, user_id=USER, carrier=None):
        mark_resumed(True)

    assert attribute(only(recorded_span), RESUMED_ATTRIBUTE) is True
