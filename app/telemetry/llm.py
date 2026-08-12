"""模型调用在 trace 上的那一段。

**与 `metric/llm.py` 是两件事，因此是两个回调。** 那边攒的是「所有调用的耗时分布」，
一屋子仪表盘；这边给的是「**这一次** run 里第 3 轮调用花了 47 秒」，一条时间轴上的
一格。把两者塞进同一个处理器会让它同时对两套语义负责，而它们的失效方式完全不同 ——
指标丢一个样本没人看得出来，trace 少一段则整条链路对不上。

验收 ① 要的「LLM 那一段的耗时」就是这些 span。
"""

import logging
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.outputs import LLMResult
from opentelemetry import trace
from opentelemetry.trace import Span, SpanKind, StatusCode

logger = logging.getLogger(__name__)

SPAN_NAME = "llm.call"

MODEL_ATTRIBUTE = "zuel.llm.model"

tracer = trace.get_tracer(__name__)


def callback() -> AsyncCallbackHandler:
    """给模型挂的追踪回调。

    Returns:
        每次调用开一个 span、结束时关掉的处理器。
    """
    return _CallSpan()


class _CallSpan(AsyncCallbackHandler):
    """一次模型调用一个 span。

    **span 不做成当前上下文**（用 `start_span` 而不是 `start_as_current_span`）：
    一次分析里多轮调用是交错的，而「当前 span」只有一个 —— 让它们互相顶替的话，
    后开的那个会认前一个当父，时间轴上就成了一串莫名其妙的嵌套。
    父由开始那一刻的上下文决定，也就是罩在外面的 `run.execute`。
    """

    def __init__(self) -> None:
        self._open: dict[UUID, Span] = {}

    async def on_chat_model_start(
        self,
        serialized: dict[str, object],
        messages: list[list[BaseMessage]],
        *,
        run_id: UUID,
        **kwargs: object,
    ) -> None:
        """开一段。"""
        span = tracer.start_span(SPAN_NAME, kind=SpanKind.CLIENT)
        name = serialized.get("name")
        if isinstance(name, str):
            span.set_attribute(MODEL_ATTRIBUTE, name)
        self._open[run_id] = span

    async def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs: object) -> None:
        """正常返回。"""
        span = self._open.pop(run_id, None)
        if span is None:
            logger.warning("模型调用结束时找不到它的 span，这一次不入 trace：run_id=%s", run_id)
            return
        span.end()

    async def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs: object) -> None:
        """抛了。

        **把异常记进 span** —— 限流与超时在时间轴上长得一样（都是一段等待），
        只有这里的状态分得开。
        """
        span = self._open.pop(run_id, None)
        if span is None:
            logger.warning("模型调用出错时找不到它的 span，这一次不入 trace：run_id=%s", run_id)
            return
        span.set_status(StatusCode.ERROR, str(error))
        span.record_exception(error)
        span.end()
