"""执行器的测试，用假 agent 与假沙箱池 —— 一律不打真实模型 API。

**执行器只跑 worker 那一半**：入口是一条已经领到手的任务，不是一次提交。
「提交之后是不是立刻返回」在 submitter_test.py 里，「领到之后 ack 不 ack」
在 test/worker/ 里。
"""

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from io import StringIO
from uuid import uuid4

import pytest
from deepagents.backends.protocol import BackendProtocol
from langchain_core.messages import AIMessage, AIMessageChunk
from redis.asyncio import Redis

from event.mapper import StreamChunk
from event.model import EventType, RunErrorCode, RunFinishedData, RunStatus, TokenUsage
from log import JsonFormatter
from run.executor import AgentRunner, RunExecutor
from run.log import EventLog
from sandbox.pool import SandboxQueueTimeoutError
from sandbox.remote import AsyncQueuePositionCallback
from task.queue import RunTask

THREAD = "thread-1"


class FakePool:
    """记录借还次数的假池，可以被要求排队或直接超时。

    申请**不返回容器**：拆出 broker 之后容器在那边，api 进程碰不到也不需要碰。
    """

    def __init__(self) -> None:
        self.acquired: list[str] = []
        self.released: list[str] = []
        self.queue_position: list[int] = []
        self.fail_with: Exception | None = None

    async def acquire(self, thread_id: str, *, on_queued: AsyncQueuePositionCallback | None = None) -> None:
        for position in self.queue_position:
            if on_queued is not None:
                await on_queued(position)
        if self.fail_with is not None:
            raise self.fail_with
        self.acquired.append(thread_id)

    async def release(self, thread_id: str) -> None:
        self.released.append(thread_id)


class FakeWorkspace:
    """按会话报出产物标识的假 workspace。真的产物判定在 broker 侧验。"""

    def __init__(self) -> None:
        self.produced: dict[str, list[str]] = {}
        self.asked: list[tuple[str, float]] = []

    async def artifact_since(self, thread_id: str, since_ns: int) -> list[str]:
        self.asked.append((thread_id, since_ns))
        return self.produced.get(thread_id, [])


class FakeRepository:
    """记下状态流转的假仓储。

    **建行不在这里**：那一步在提交侧（submitter），worker 领到任务时那一行早就有了。
    真的那一套 SQL 在 test/run/repository_test.py 里连真库验。
    """

    def __init__(self) -> None:
        self.status: dict[str, RunStatus] = {}
        self.tokens: dict[str, TokenUsage] = {}
        self.error: dict[str, tuple[RunErrorCode, str]] = {}

    async def start(self, run_id: str) -> None:
        self.status[run_id] = RunStatus.RUNNING

    async def succeed(self, run_id: str, *, tokens: TokenUsage) -> bool:
        if not self._open(run_id):
            return False
        self.tokens[run_id] = tokens
        self.status[run_id] = RunStatus.SUCCEEDED
        return True

    async def fail(self, run_id: str, *, code: RunErrorCode, message: str) -> bool:
        if not self._open(run_id):
            return False
        self.error[run_id] = (code, message)
        self.status[run_id] = RunStatus.FAILED
        return True

    async def cancel(self, run_id: str, *, tokens: TokenUsage | None = None) -> bool:
        if not self._open(run_id):
            return False
        if tokens is not None:
            self.tokens[run_id] = tokens
        self.status[run_id] = RunStatus.CANCELLED
        return True

    def _open(self, run_id: str) -> bool:
        """条件更新的替身：已经有终态的 run 写不进去。"""
        return self.status.get(run_id) in (None, RunStatus.QUEUED, RunStatus.RUNNING)


class FakeCancelFlag:
    """可以在任意一个 step 边界上被举起来的假标志。"""

    def __init__(self) -> None:
        self.raised: set[str] = set()
        self.checked: list[str] = []

    async def is_raised(self, run_id: str) -> bool:
        self.checked.append(run_id)
        return run_id in self.raised

    def raise_flag(self, run_id: str) -> None:
        self.raised.add(run_id)


def chunk_stream(*chunk: StreamChunk) -> AsyncIterator[StreamChunk]:
    async def stream() -> AsyncIterator[StreamChunk]:
        for one in chunk:
            await asyncio.sleep(0)
            yield one

    return stream()


def token_chunk(text: str) -> StreamChunk:
    return ((), "messages", (AIMessageChunk(content=text), {}))


def usage_chunk(input_token: int, output_token: int, cache_read: int = 0) -> StreamChunk:
    """一个带用量的 chunk。`input_token` 是含命中部分的总数，与 DeepSeek 的口径一致。"""
    message = AIMessage(
        content="",
        usage_metadata={
            "input_tokens": input_token,
            "output_tokens": output_token,
            "total_tokens": 0,
            "input_token_details": {"cache_read": cache_read},
        },
    )
    return ((), "updates", {"model": {"messages": [message]}})


@pytest.fixture
def pool() -> FakePool:
    return FakePool()


@pytest.fixture
def space() -> FakeWorkspace:
    return FakeWorkspace()


@pytest.fixture
def log(live_cache: Redis) -> EventLog:
    return EventLog(live_cache)


def a_task(thread_id: str = THREAD, content: str = "一") -> RunTask:
    """一条队列里领到的任务。真实的 run id 就是 uuid4().hex。"""
    return RunTask(run_id=uuid4().hex, thread_id=thread_id, content=content)


def make_executor(
    pool: FakePool, space: FakeWorkspace, log: EventLog, *chunk: StreamChunk
) -> tuple[RunExecutor, FakeRepository]:
    def runner(backend: BackendProtocol, thread_id: str, content: str) -> AsyncIterator[StreamChunk]:
        return chunk_stream(*chunk)

    return make_executor_with(pool, space, log, runner)


def make_executor_with(
    pool: FakePool,
    space: FakeWorkspace,
    log: EventLog,
    runner: AgentRunner,
    cancel: FakeCancelFlag | None = None,
) -> tuple[RunExecutor, FakeRepository]:
    repository = FakeRepository()
    executor = RunExecutor(
        pool=pool,
        workspace=space,
        log=log,
        runner=runner,
        repository=repository,
        cancel=cancel or FakeCancelFlag(),
    )
    return executor, repository


async def artifacts_of(log: EventLog, run_id: str) -> list[str]:
    return (await _finished(log, run_id)).artifacts


async def tokens_of(log: EventLog, run_id: str) -> TokenUsage:
    return (await _finished(log, run_id)).tokens


async def _finished(log: EventLog, run_id: str) -> RunFinishedData:
    data = (await log.read(run_id))[-1].event.data
    assert isinstance(data, RunFinishedData)
    return data


async def types_of(log: EventLog, run_id: str) -> list[str]:
    return [one.event.model_dump()["type"] for one in await log.read(run_id)]


# ------------------------------------------------------------------ 状态流转
async def test_a_finished_run_ends_up_succeeded(pool: FakePool, space: FakeWorkspace, log: EventLog) -> None:
    executor, repository = make_executor(pool, space, log, token_chunk("好"))
    run = a_task()

    await executor.execute(run)

    assert repository.status[run.run_id] is RunStatus.SUCCEEDED


# ------------------------------------------------------------------ 事件序列
async def test_the_event_sequence_brackets_the_agent_output(
    pool: FakePool, space: FakeWorkspace, log: EventLog
) -> None:
    executor, _ = make_executor(pool, space, log, token_chunk("好"), token_chunk("的"))

    run = a_task(content="一")
    await executor.execute(run)

    assert await types_of(log, run.run_id) == ["run.started", "sandbox.ready", "token", "token", "run.finished"]


async def test_run_started_carries_the_thread(pool: FakePool, space: FakeWorkspace, log: EventLog) -> None:
    executor, _ = make_executor(pool, space, log)

    run = a_task(content="一")
    await executor.execute(run)

    started = (await log.read(run.run_id))[0].event
    assert started.data.thread_id == THREAD  # type: ignore[union-attr]


async def test_every_event_carries_the_run_id(pool: FakePool, space: FakeWorkspace, log: EventLog) -> None:
    """前端可能同时订阅多个 run，信封里没有 run_id 就没法路由。"""
    executor, _ = make_executor(pool, space, log, token_chunk("好"))

    run = a_task(content="一")
    await executor.execute(run)

    assert {one.event.run_id for one in (await log.read(run.run_id))} == {run.run_id}


async def test_event_ids_increase_monotonically_across_the_whole_run(
    pool: FakePool, space: FakeWorkspace, log: EventLog
) -> None:
    executor, _ = make_executor(pool, space, log, *[token_chunk(str(index)) for index in range(30)])

    run = a_task(content="一")
    await executor.execute(run)

    ids = [one.id for one in (await log.read(run.run_id))]
    assert ids == sorted(ids, key=lambda one: tuple(int(part) for part in one.split("-")))


async def test_events_of_two_concurrent_runs_do_not_mix(pool: FakePool, space: FakeWorkspace, log: EventLog) -> None:
    executor, _ = make_executor(pool, space, log, token_chunk("好"))

    first, second = a_task(thread_id="thread-1"), a_task(thread_id="thread-2")
    await asyncio.gather(executor.execute(first), executor.execute(second))

    assert await types_of(log, first.run_id) == await types_of(log, second.run_id)
    assert await types_of(log, first.run_id) == ["run.started", "sandbox.ready", "token", "run.finished"]


# ------------------------------------------------------------------ token 计量
async def test_run_finished_accumulates_the_tokens_across_model_calls(
    pool: FakePool, space: FakeWorkspace, log: EventLog
) -> None:
    executor, _ = make_executor(pool, space, log, usage_chunk(2916, 120), usage_chunk(4100, 80))

    run = a_task(content="一")
    await executor.execute(run)

    assert await tokens_of(log, run.run_id) == TokenUsage(
        input_cache_read=0, input_uncached=2916 + 4100, output=120 + 80
    )


async def test_cache_hits_are_reported_apart_from_the_rest(pool: FakePool, space: FakeWorkspace, log: EventLog) -> None:
    """§6.4：按 input 总数记会高估成本约 1.6 倍，两部分单价差得远，不能合并。"""
    executor, _ = make_executor(pool, space, log, usage_chunk(304640, 8701, cache_read=189312))

    run = a_task(content="一")
    await executor.execute(run)

    assert await tokens_of(log, run.run_id) == TokenUsage(
        input_cache_read=189312,
        input_uncached=304640 - 189312,
        output=8701,
    )


async def test_a_missing_cache_detail_counts_as_no_hit(pool: FakePool, space: FakeWorkspace, log: EventLog) -> None:
    """换个不带 prompt cache 的模型时 `input_token_details` 整个不存在，不能因此崩掉。"""
    message = AIMessage(content="", usage_metadata={"input_tokens": 100, "output_tokens": 7, "total_tokens": 107})
    executor, _ = make_executor(pool, space, log, ((), "updates", {"model": {"messages": [message]}}))

    run = a_task(content="一")
    await executor.execute(run)

    assert await tokens_of(log, run.run_id) == TokenUsage(input_cache_read=0, input_uncached=100, output=7)


async def test_tokens_are_zero_when_the_model_reports_no_usage(
    pool: FakePool, space: FakeWorkspace, log: EventLog
) -> None:
    executor, _ = make_executor(pool, space, log, token_chunk("好"))

    run = a_task(content="一")
    await executor.execute(run)

    assert await tokens_of(log, run.run_id) == TokenUsage()


# ------------------------------------------------------------------ 排障日志
async def test_logs_emitted_during_a_run_carry_its_ids(pool: FakePool, space: FakeWorkspace, log: EventLog) -> None:
    """排障要能按 run_id 过滤出一次执行的全部日志，执行器是这两个 id 的来源。"""
    sink = StringIO()
    handler = logging.StreamHandler(sink)
    handler.setFormatter(JsonFormatter())
    probe = logging.getLogger("test.executor.probe")
    probe.addHandler(handler)
    probe.setLevel(logging.INFO)

    def noisy(backend: BackendProtocol, thread_id: str, content: str) -> AsyncIterator[StreamChunk]:
        async def stream() -> AsyncIterator[StreamChunk]:
            probe.info("执行中")
            await asyncio.sleep(0)
            yield token_chunk("好")

        return stream()

    executor, _ = make_executor_with(pool, space, log, noisy)
    run = a_task()
    try:
        await executor.execute(run)
    finally:
        probe.removeHandler(handler)

    line = json.loads(sink.getvalue())
    assert line["run_id"] == run.run_id
    assert line["thread_id"] == THREAD


# ------------------------------------------------------------------ 沙箱
async def test_the_sandbox_is_released_after_the_run(pool: FakePool, space: FakeWorkspace, log: EventLog) -> None:
    executor, _ = make_executor(pool, space, log)

    run = a_task(content="一")
    await executor.execute(run)

    assert pool.acquired == [THREAD]
    assert pool.released == [THREAD]


async def test_the_sandbox_is_released_even_when_the_agent_blows_up(
    pool: FakePool, space: FakeWorkspace, log: EventLog
) -> None:
    """不归还就是永久漏掉一个名额，几次之后整台机器就没有沙箱可用了。"""

    def exploding(backend: BackendProtocol, thread_id: str, content: str) -> AsyncIterator[StreamChunk]:
        async def stream() -> AsyncIterator[StreamChunk]:
            await asyncio.sleep(0)
            raise RuntimeError("模型连接断了")
            yield  # pragma: no cover - 让函数成为异步生成器

        return stream()

    executor, _ = make_executor_with(pool, space, log, exploding)

    run = a_task(content="一")
    await executor.execute(run)

    assert pool.released == [THREAD]


async def test_queue_positions_are_emitted_as_events(pool: FakePool, space: FakeWorkspace, log: EventLog) -> None:
    pool.queue_position = [3, 2, 1]
    executor, _ = make_executor(pool, space, log)

    run = a_task(content="一")
    await executor.execute(run)

    queued = [one.event for one in (await log.read(run.run_id)) if one.event.type is EventType.SANDBOX_QUEUED]
    assert [one.data.position for one in queued] == [3, 2, 1]
    assert (await types_of(log, run.run_id))[:5] == [
        "run.started",
        "sandbox.queued",
        "sandbox.queued",
        "sandbox.queued",
        "sandbox.ready",
    ]


async def test_waiting_too_long_for_a_sandbox_fails_the_run_as_retryable(
    pool: FakePool, space: FakeWorkspace, log: EventLog
) -> None:
    """排队超时是资源不足，不是请求有问题 —— 过一会儿重试是有意义的。"""
    pool.fail_with = SandboxQueueTimeoutError("等待沙箱超过 600 秒")
    executor, repository = make_executor(pool, space, log)

    run = a_task(content="一")
    await executor.execute(run)

    failed = (await log.read(run.run_id))[-1].event
    assert failed.type is EventType.RUN_FAILED
    assert failed.data.code is RunErrorCode.SANDBOX_QUEUE_TIMEOUT
    assert failed.data.retryable is True
    assert repository.status[run.run_id] is RunStatus.FAILED


async def test_a_failed_sandbox_acquisition_is_not_released(
    pool: FakePool, space: FakeWorkspace, log: EventLog
) -> None:
    pool.fail_with = SandboxQueueTimeoutError("等待沙箱超过 600 秒")
    executor, _ = make_executor(pool, space, log)

    run = a_task(content="一")
    await executor.execute(run)

    assert pool.released == []


# ------------------------------------------------------------------ 失败
async def test_an_agent_error_ends_the_run_as_failed(pool: FakePool, space: FakeWorkspace, log: EventLog) -> None:
    def exploding(backend: BackendProtocol, thread_id: str, content: str) -> AsyncIterator[StreamChunk]:
        async def stream() -> AsyncIterator[StreamChunk]:
            yield token_chunk("刚开了个头")
            raise RuntimeError("模型连接断了")

        return stream()

    executor, repository = make_executor_with(pool, space, log, exploding)

    run = a_task(content="一")
    await executor.execute(run)

    assert await types_of(log, run.run_id) == ["run.started", "sandbox.ready", "token", "run.failed"]
    assert repository.status[run.run_id] is RunStatus.FAILED


async def test_an_unclassified_error_is_not_retryable(pool: FakePool, space: FakeWorkspace, log: EventLog) -> None:
    """未分类异常按永久错误处理，盲目重试只会再炸一次还多花一份 token。"""

    def exploding(backend: BackendProtocol, thread_id: str, content: str) -> AsyncIterator[StreamChunk]:
        async def stream() -> AsyncIterator[StreamChunk]:
            raise RuntimeError("谁知道呢")
            yield  # pragma: no cover - 让函数成为异步生成器

        return stream()

    executor, _ = make_executor_with(pool, space, log, exploding)

    run = a_task(content="一")
    await executor.execute(run)

    failed = (await log.read(run.run_id))[-1].event
    assert failed.data.code is RunErrorCode.INTERNAL  # type: ignore[union-attr]
    assert failed.data.retryable is False  # type: ignore[union-attr]


async def test_a_failing_run_always_gets_a_terminal_event(pool: FakePool, space: FakeWorkspace, log: EventLog) -> None:
    """没有终态事件，订阅这个 run 的 SSE 连接会永远挂着。"""
    pool.fail_with = OSError("workspace 所在磁盘不可用")
    executor, _ = make_executor(pool, space, log)

    run = a_task(content="一")
    await executor.execute(run)

    assert (await types_of(log, run.run_id))[-1] == "run.failed"


# ------------------------------------------------------------------ 与事件流的衔接
async def test_a_follower_sees_the_whole_run_from_start_to_finish(
    pool: FakePool, space: FakeWorkspace, log: EventLog
) -> None:
    """步骤四的 SSE 端点就是这么用的：订阅先于事件产生。"""
    executor, _ = make_executor(pool, space, log, token_chunk("好"), token_chunk("的"))
    run = a_task()

    driving = asyncio.create_task(executor.execute(run))
    received = [one.event.model_dump()["type"] async for one in log.follow(run.run_id)]
    await driving

    assert received == ["run.started", "sandbox.ready", "token", "token", "run.finished"]


# ------------------------------------------------------------------ 产物
# 「哪些文件算产物」的判定在 broker 侧（见 test/broker/），这里只验执行器有没有
# 在正确的时间点去问、以及有没有把答案原样放进 run.finished。
async def test_run_finished_lists_what_this_run_produced(pool: FakePool, space: FakeWorkspace, log: EventLog) -> None:
    """产物端点靠这些标识拼 URL，不给的话教师只能从答复文本里猜路径。"""
    space.produced[THREAD] = [f"{THREAD}/chart.png"]
    executor, _ = make_executor(pool, space, log, token_chunk("画好了"))

    run = a_task(content="画个图")
    await executor.execute(run)

    assert await artifacts_of(log, run.run_id) == [f"{THREAD}/chart.png"]


async def test_a_run_that_produced_nothing_reports_an_empty_list(
    pool: FakePool, space: FakeWorkspace, log: EventLog
) -> None:
    executor, _ = make_executor(pool, space, log, token_chunk("说明一下就好"))

    run = a_task(content="解释一下")
    await executor.execute(run)

    assert await artifacts_of(log, run.run_id) == []


async def test_artifacts_are_asked_for_from_before_the_agent_started(
    pool: FakePool, space: FakeWorkspace, log: EventLog
) -> None:
    """基准晚于 agent 动手的话，本轮自己的产出会被判成「上一轮的」而漏掉。"""
    before = time.time_ns()
    executor, _ = make_executor(pool, space, log, token_chunk("好"))

    run = a_task(content="一")
    await executor.execute(run)

    asked_thread, asked_since = space.asked[0]
    assert asked_thread == THREAD
    assert before <= asked_since <= time.time_ns()


# ------------------------------------------------------------------ 主动取消
async def test_a_cancelled_run_stops_at_the_next_step_boundary(
    pool: FakePool, space: FakeWorkspace, log: EventLog
) -> None:
    """标志在第一个 step 边界上就被看到，后面的 chunk 一个都不该再被消费。"""
    cancel = FakeCancelFlag()
    consumed: list[str] = []

    def runner(backend: BackendProtocol, thread_id: str, content: str) -> AsyncIterator[StreamChunk]:
        async def stream() -> AsyncIterator[StreamChunk]:
            yield usage_chunk(100, 10)
            consumed.append("第二步")
            yield usage_chunk(100, 10)

        return stream()

    executor, repository = make_executor_with(pool, space, log, runner, cancel)
    run = a_task()
    cancel.raise_flag(run.run_id)

    await executor.execute(run)

    assert repository.status[run.run_id] is RunStatus.CANCELLED
    assert consumed == []


async def test_a_cancelled_run_pushes_its_own_event(pool: FakePool, space: FakeWorkspace, log: EventLog) -> None:
    """终态是 `run.cancelled` 而不是 `run.failed` —— 取消不是故障，前端不该显示重试。"""
    cancel = FakeCancelFlag()
    executor, _ = make_executor_with(pool, space, log, lambda *_: chunk_stream(usage_chunk(100, 10)), cancel)
    run = a_task()
    cancel.raise_flag(run.run_id)

    await executor.execute(run)

    assert (await types_of(log, run.run_id))[-1] == EventType.RUN_CANCELLED.value


async def test_a_cancelled_run_stops_burning_tokens(pool: FakePool, space: FakeWorkspace, log: EventLog) -> None:
    """步骤四验证②：事件流停了只说明没人在推，不说明模型调用停了 —— 而那是真金白银。

    第一步的 100 token 已经花掉，退不回来；第二步那 9999 一个都不该出现在账上。
    """
    cancel = FakeCancelFlag()
    executor, repository = make_executor_with(
        pool, space, log, lambda *_: chunk_stream(usage_chunk(100, 10), usage_chunk(9999, 9999)), cancel
    )
    run = a_task()
    cancel.raise_flag(run.run_id)

    await executor.execute(run)

    assert repository.tokens[run.run_id].input_uncached == 0


async def test_a_run_cancelled_midway_keeps_what_it_already_burned(
    pool: FakePool, space: FakeWorkspace, log: EventLog
) -> None:
    """取消那一刻的用量要记下来 —— 教师下一个要问的就是「这次白花了多少」。"""
    cancel = FakeCancelFlag()
    run = a_task()

    def runner(backend: BackendProtocol, thread_id: str, content: str) -> AsyncIterator[StreamChunk]:
        async def stream() -> AsyncIterator[StreamChunk]:
            yield usage_chunk(100, 10)
            cancel.raise_flag(run.run_id)
            yield usage_chunk(200, 20)

        return stream()

    executor, repository = make_executor_with(pool, space, log, runner, cancel)

    await executor.execute(run)

    assert repository.status[run.run_id] is RunStatus.CANCELLED
    assert repository.tokens[run.run_id].input_uncached == 300


async def test_a_cancelled_run_gives_its_sandbox_back(pool: FakePool, space: FakeWorkspace, log: EventLog) -> None:
    """沙箱在 finally 里归还，取消这条路径不能绕过它 —— 绕过去就是永久少一个名额。"""
    cancel = FakeCancelFlag()
    run = a_task()

    def runner(backend: BackendProtocol, thread_id: str, content: str) -> AsyncIterator[StreamChunk]:
        async def stream() -> AsyncIterator[StreamChunk]:
            cancel.raise_flag(run.run_id)
            yield usage_chunk(100, 10)

        return stream()

    executor, _ = make_executor_with(pool, space, log, runner, cancel)

    await executor.execute(run)

    assert pool.released == [THREAD]


async def test_a_run_cancelled_while_queued_never_starts(pool: FakePool, space: FakeWorkspace, log: EventLog) -> None:
    """步骤四验证④：任务消息还躺在队列里，worker 迟早会领到它。

    不在开跑前挡一道的话，那次取消就只是改了个状态，而分析照跑不误。
    """
    cancel = FakeCancelFlag()
    asked: list[str] = []

    def runner(backend: BackendProtocol, thread_id: str, content: str) -> AsyncIterator[StreamChunk]:
        asked.append(content)
        return chunk_stream(token_chunk("好"))

    executor, repository = make_executor_with(pool, space, log, runner, cancel)
    run = a_task()
    cancel.raise_flag(run.run_id)

    await executor.execute(run)

    assert asked == []
    assert repository.status[run.run_id] is RunStatus.CANCELLED
    assert await types_of(log, run.run_id) == [EventType.RUN_CANCELLED.value]


async def test_a_run_that_someone_else_already_cancelled_stays_quiet(
    pool: FakePool, space: FakeWorkspace, log: EventLog
) -> None:
    """Api 抢先改过状态时，worker 不该再推一条 —— 否则教师看到两次「已取消」。"""
    cancel = FakeCancelFlag()
    executor, repository = make_executor_with(pool, space, log, lambda *_: chunk_stream(), cancel)
    run = a_task()
    cancel.raise_flag(run.run_id)
    repository.status[run.run_id] = RunStatus.CANCELLED

    await executor.execute(run)

    assert await types_of(log, run.run_id) == []


async def test_an_uncancelled_run_still_checks_the_flag(pool: FakePool, space: FakeWorkspace, log: EventLog) -> None:
    """没人取消时照常跑完 —— 上面几条不能是「加了个标志就谁都跑不动」。"""
    cancel = FakeCancelFlag()
    executor, repository = make_executor_with(pool, space, log, lambda *_: chunk_stream(usage_chunk(100, 10)), cancel)
    run = a_task()

    await executor.execute(run)

    assert repository.status[run.run_id] is RunStatus.SUCCEEDED
    assert cancel.checked
