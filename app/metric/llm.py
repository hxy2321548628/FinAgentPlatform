"""LLM 调用的指标：一次调用有多慢、失不失败。

**这是本包里唯一长生命周期的指标**。前面那些 gauge 抓取时现查就有，而「一次调用花了
多久」只有调用发生的那一刻量得到 —— 事后无论查哪张表都还原不出来，因此必须在进程里
攒着。攒的地方是 worker：它是唯一调用模型的进程。

挂载方式是 LangChain 的回调。**挂在模型上而不是挂在每次调用上** —— agent 内部一次分析
要调十几轮模型，逐次挂载等于把「别忘了挂」这件事重复十几遍，而漏了不会报错，只会让
那一段在图上消失。

延迟与失败率共用一个直方图，靠 `outcome` 标签分开：失败调用的耗时同样值得看
（一次超时是 60 秒，一次 400 是 200 毫秒，两者的排障方向完全不同）。
"""

import logging
import time
from collections.abc import Callable
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.outputs import LLMResult
from prometheus_client import CollectorRegistry, Histogram

from metric.exposition import NAMESPACE, create_registry

logger = logging.getLogger(__name__)

OK_OUTCOME = "ok"
ERROR_OUTCOME = "error"

# 分桶。**默认桶最大只到 10 秒，而一次分析型调用动辄几十秒** —— 用默认桶的话
# 所有调用都落进 `+Inf`，p95 会变成一条毫无信息的直线
LATENCY_BUCKET = (0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0, 120.0, float("inf"))

Clock = Callable[[], float]


class LlmMetric:
    """模型调用的延迟与失败率，以及导出它们的注册表。

    Args:
        clock: 单调时钟，只在测试里换成可控的。
    """

    def __init__(self, *, clock: Clock = time.monotonic) -> None:
        self._registry = create_registry()
        self._call = Histogram(
            "llm_call_second",
            "一次模型调用的耗时，秒。失败的那些也在里面，按 outcome 分开",
            labelnames=("outcome",),
            buckets=LATENCY_BUCKET,
            namespace=NAMESPACE,
            registry=self._registry,
        )
        self._clock = clock

    @property
    def registry(self) -> CollectorRegistry:
        """这些指标所在的注册表。"""
        return self._registry

    def callback(self) -> AsyncCallbackHandler:
        """给模型挂的回调。

        Returns:
            记录每次调用起止的处理器。
        """
        return _CallWatch(self._call, self._clock)


class _CallWatch(AsyncCallbackHandler):
    """在模型调用的起止两端打点。

    **异步而不是同步处理器**：agent 整条链路都是异步的，给同步处理器时 LangChain 会
    把每次回调丢进线程池，为了一次 `time.monotonic()` 多一趟线程切换。
    """

    def __init__(self, call: Histogram, clock: Clock) -> None:
        self._call = call
        self._clock = clock
        self._started: dict[UUID, float] = {}

    async def on_chat_model_start(
        self,
        serialized: dict[str, object],
        messages: list[list[BaseMessage]],
        *,
        run_id: UUID,
        **kwargs: object,
    ) -> None:
        """记下这次调用的起点。"""
        self._started[run_id] = self._clock()

    async def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs: object) -> None:
        """调用成功返回。"""
        self._observe(run_id, OK_OUTCOME)

    async def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs: object) -> None:
        """调用抛了 —— 限流、超时、鉴权，都在这里。"""
        self._observe(run_id, ERROR_OUTCOME)

    def _observe(self, run_id: UUID, outcome: str) -> None:
        """结掉一次调用。**起点丢了就不记**，编一个耗时比缺一个样本更坏。"""
        started = self._started.pop(run_id, None)
        if started is None:
            logger.warning("模型调用结束时找不到它的起点，这一次不计延迟：run_id=%s", run_id)
            return
        self._call.labels(outcome=outcome).observe(self._clock() - started)
