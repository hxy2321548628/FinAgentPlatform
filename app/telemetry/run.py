"""一个 run 在 trace 上的那一段：worker 侧的根 span，以及往上面钉的结论。

**验收 ①「给一个 run_id，拿到它各段的耗时与这次的 token」，靠的就是这里的属性。**
Tempo 按属性检索：没有 `zuel.run_id` 这个属性，「按 run_id 找那条 trace」就无从谈起，
只能靠时间范围加人眼 —— 而那与「日志里都有，自己 grep」是同一件事，正是本期要摆脱的。
"""

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.trace import Span, SpanKind

from event.model import Event, EventType, RunCancelledData, RunFinishedData, TokenUsage
from telemetry.context import resume

SPAN_NAME = "run.execute"

# 检索用的属性。**前缀是自己的命名空间**：OTel 的语义约定里没有「run」这回事，
# 不加前缀迟早会跟某个自动探针撞名
RUN_ATTRIBUTE = "zuel.run_id"
THREAD_ATTRIBUTE = "zuel.thread_id"
USER_ATTRIBUTE = "zuel.user_id"
RESUMED_ATTRIBUTE = "zuel.resumed"
STATUS_ATTRIBUTE = "zuel.status"

# token 三元组。名字与 `run.finished` 事件的字段一致，不另起一套
CACHE_READ_ATTRIBUTE = "zuel.token.input_cache_read"
UNCACHED_ATTRIBUTE = "zuel.token.input_uncached"
OUTPUT_ATTRIBUTE = "zuel.token.output"

# 走到这三个之一，这一个 run 就结束了
TERMINAL_TYPE = (EventType.RUN_FINISHED, EventType.RUN_FAILED, EventType.RUN_CANCELLED)

tracer = trace.get_tracer(__name__)


@contextmanager
def execution(*, run_id: str, thread_id: str, user_id: str | None, carrier: dict[str, str] | None) -> Iterator[Span]:
    """罩住 worker 里执行一条任务的全过程。

    父 span 从任务消息里带来的上下文恢复 —— 那是 api 与 worker 之间唯一的接缝
    （中间隔着队列，没有请求头可用）。

    **一个 run 可能罩出好几段**：每轮审批之后都会重新投递一次，崩溃重投也是。
    它们共享同一个 `zuel.run_id`，因此按 run_id 检索会把这几段都找出来 ——
    那正是想要的，「这个 run 前前后后花了多久」本来就该包含挂起的那几程。

    Args:
        run_id: 这一个 run。
        thread_id: 它所属的会话。
        user_id: 提交的人。为空表示这条任务没有归属（旧消息）。
        carrier: 任务消息里带来的 trace 上下文。

    Yields:
        这一段执行的 span。
    """
    with tracer.start_as_current_span(SPAN_NAME, context=resume(carrier), kind=SpanKind.CONSUMER) as span:
        span.set_attribute(RUN_ATTRIBUTE, run_id)
        span.set_attribute(THREAD_ATTRIBUTE, thread_id)
        if user_id is not None:
            span.set_attribute(USER_ATTRIBUTE, user_id)
        yield span


def mark_resumed(resumed: bool) -> None:
    """标上这一程是不是「接着刚才那一程」。

    Args:
        resumed: 崩溃恢复或审批续跑为 True。
    """
    trace.get_current_span().set_attribute(RESUMED_ATTRIBUTE, resumed)


def record(event: Event) -> None:
    """把终态事件的结论钉到当前 span 上，非终态事件忽略。

    **取的是「当前」span 而不是传进来一个** —— 执行器有七八处会发事件，逐处把 span
    传下去等于让每一处都记得这件事，而漏一处不会报错，只会让那条 trace 少一半信息。
    OTel 的上下文本来就是干这个的：`execution()` 罩着的范围内，当前 span 就是它。

    Args:
        event: 刚发出去的事件。
    """
    if event.type not in TERMINAL_TYPE:
        return
    span = trace.get_current_span()
    span.set_attribute(STATUS_ATTRIBUTE, event.type.value)
    _record_token(span, event)


def _record_token(span: Span, event: Event) -> None:
    """带用量的那两种终态才有 token 可记。`run.failed` 没有 —— 它只有原因。"""
    data = getattr(event, "data", None)
    if not isinstance(data, RunFinishedData | RunCancelledData):
        return
    tokens: TokenUsage = data.tokens
    span.set_attribute(CACHE_READ_ATTRIBUTE, tokens.input_cache_read)
    span.set_attribute(UNCACHED_ATTRIBUTE, tokens.input_uncached)
    span.set_attribute(OUTPUT_ATTRIBUTE, tokens.output)
