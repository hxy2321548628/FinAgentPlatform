"""LLM 调用指标的测试。

延迟是**唯一事后还原不出来的那个数** —— 库里、日志里都没有，只有调用发生的那一刻量得到。
因此这里把回调直接驱动一遍，而不是断言「模型被调用了」。

时钟是注入的：拿真实时间断言耗时，用例就只能断「大于 0」，而那条断言在把秒当毫秒
用的时候照样是绿的。
"""

from uuid import uuid4

from langchain_core.outputs import LLMResult

from metric.llm import ERROR_OUTCOME, OK_OUTCOME, LlmMetric

COUNT_METRIC = "zuel_llm_call_second_count"
SUM_METRIC = "zuel_llm_call_second_sum"
BUCKET_METRIC = "zuel_llm_call_second_bucket"

EMPTY_RESULT = LLMResult(generations=[])


class FakeClock:
    """走一步跳一格的时钟。"""

    def __init__(self, step: float) -> None:
        self.now = 0.0
        self._step = step

    def __call__(self) -> float:
        current = self.now
        self.now += self._step
        return current


def counted(metric: LlmMetric, outcome: str) -> float | None:
    return metric.registry.get_sample_value(COUNT_METRIC, {"outcome": outcome})


def summed(metric: LlmMetric, outcome: str) -> float | None:
    return metric.registry.get_sample_value(SUM_METRIC, {"outcome": outcome})


async def test_a_finished_call_is_timed() -> None:
    metric = LlmMetric(clock=FakeClock(step=7.0))
    handler = metric.callback()
    call = uuid4()

    await handler.on_chat_model_start({}, [], run_id=call)
    await handler.on_llm_end(EMPTY_RESULT, run_id=call)

    assert counted(metric, OK_OUTCOME) == 1
    assert summed(metric, OK_OUTCOME) == 7.0


async def test_a_failed_call_is_timed_too() -> None:
    """一次超时是 60 秒、一次 400 是 200 毫秒，排障方向完全不同，都得留下来。"""
    metric = LlmMetric(clock=FakeClock(step=60.0))
    handler = metric.callback()
    call = uuid4()

    await handler.on_chat_model_start({}, [], run_id=call)
    await handler.on_llm_error(TimeoutError(), run_id=call)

    assert counted(metric, ERROR_OUTCOME) == 1
    assert summed(metric, ERROR_OUTCOME) == 60.0
    assert counted(metric, OK_OUTCOME) is None


async def test_concurrent_calls_do_not_get_each_others_latency() -> None:
    """一个 worker 同时驱动多个 run，模型调用天然是交错的。

    按 `run_id` 认自己的起点，不是按「最近一次开始」—— 后者会把 A 的耗时算给 B，
    而两条都还是合法的数字，看板上什么都看不出来。
    """
    clock = FakeClock(step=1.0)
    metric = LlmMetric(clock=clock)
    handler = metric.callback()
    first, second = uuid4(), uuid4()

    await handler.on_chat_model_start({}, [], run_id=first)
    await handler.on_chat_model_start({}, [], run_id=second)
    await handler.on_llm_end(EMPTY_RESULT, run_id=second)
    await handler.on_llm_end(EMPTY_RESULT, run_id=first)

    # 时钟依次给出 0 1 2 3：second 用了 2-1=1，first 用了 3-0=3
    assert summed(metric, OK_OUTCOME) == 4.0
    assert counted(metric, OK_OUTCOME) == 2


async def test_an_orphan_end_is_not_counted() -> None:
    """没见过起点就不记。编一个耗时比缺一个样本更坏 —— 后者看得见，前者看不见。"""
    metric = LlmMetric(clock=FakeClock(step=1.0))
    handler = metric.callback()

    await handler.on_llm_end(EMPTY_RESULT, run_id=uuid4())

    assert counted(metric, OK_OUTCOME) is None


async def test_the_buckets_reach_past_a_minute() -> None:
    """默认桶最大只到 10 秒，而一次分析型调用动辄几十秒。

    用默认桶的话所有调用都落进 `+Inf`，p95 会变成一条毫无信息的直线。
    """
    metric = LlmMetric(clock=FakeClock(step=45.0))
    handler = metric.callback()
    call = uuid4()

    await handler.on_chat_model_start({}, [], run_id=call)
    await handler.on_llm_end(EMPTY_RESULT, run_id=call)

    assert metric.registry.get_sample_value(BUCKET_METRIC, {"outcome": OK_OUTCOME, "le": "30.0"}) == 0
    assert metric.registry.get_sample_value(BUCKET_METRIC, {"outcome": OK_OUTCOME, "le": "60.0"}) == 1
