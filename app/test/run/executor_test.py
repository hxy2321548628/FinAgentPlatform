"""执行器的测试，用假 agent 与假沙箱池 —— 一律不打真实模型 API。"""

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from io import StringIO

import pytest
from deepagents.backends.protocol import BackendProtocol
from langchain_core.messages import AIMessage, AIMessageChunk

from event.mapper import StreamChunk
from event.model import EventType, RunErrorCode, RunFinishedData, RunStatus, TokenUsage
from log import JsonFormatter
from run.executor import RunExecutor
from run.log import EventLog
from run.repository import Run
from sandbox.pool import QueuePositionCallback, SandboxQueueTimeoutError

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

    async def acquire(self, thread_id: str, *, on_queued: QueuePositionCallback | None = None) -> None:
        for position in self.queue_position:
            if on_queued is not None:
                on_queued(position)
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
    """内存里的 run 元数据。

    真的那一套 (`runs` 表) 在 test/run/repository_test.py 里连真库验；
    这里要验的是执行器的状态流转顺序，不是 SQL。
    """

    def __init__(self) -> None:
        self.run: dict[str, Run] = {}
        self.tokens: dict[str, TokenUsage] = {}
        self.error: dict[str, tuple[RunErrorCode, str]] = {}

    async def create(self, *, run_id: str, thread_id: str) -> None:
        self.run[run_id] = Run(id=run_id, thread_id=thread_id, status=RunStatus.QUEUED)

    async def get(self, run_id: str) -> Run | None:
        return self.run.get(run_id)

    async def start(self, run_id: str) -> None:
        self._move(run_id, RunStatus.RUNNING)

    async def succeed(self, run_id: str, *, tokens: TokenUsage) -> None:
        self.tokens[run_id] = tokens
        self._move(run_id, RunStatus.SUCCEEDED)

    async def fail(self, run_id: str, *, code: RunErrorCode, message: str) -> None:
        self.error[run_id] = (code, message)
        self._move(run_id, RunStatus.FAILED)

    def _move(self, run_id: str, status: RunStatus) -> None:
        current = self.run[run_id]
        self.run[run_id] = Run(id=current.id, thread_id=current.thread_id, status=status)


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
def log() -> EventLog:
    return EventLog()


def make_executor(pool: FakePool, space: FakeWorkspace, log: EventLog, *chunk: StreamChunk) -> RunExecutor:
    def runner(backend: BackendProtocol, thread_id: str, content: str) -> AsyncIterator[StreamChunk]:
        return chunk_stream(*chunk)

    return RunExecutor(pool=pool, workspace=space, log=log, runner=runner, repository=FakeRepository())


def artifacts_of(log: EventLog, run_id: str) -> list[str]:
    return _finished(log, run_id).artifacts


def tokens_of(log: EventLog, run_id: str) -> TokenUsage:
    return _finished(log, run_id).tokens


def _finished(log: EventLog, run_id: str) -> RunFinishedData:
    data = log.read(run_id)[-1].event.data
    assert isinstance(data, RunFinishedData)
    return data


def types_of(log: EventLog, run_id: str) -> list[str]:
    return [one.event.model_dump()["type"] for one in log.read(run_id)]


# ------------------------------------------------------------------ 提交
async def test_submit_returns_immediately_with_a_queued_run(
    pool: FakePool, space: FakeWorkspace, log: EventLog
) -> None:
    """任务要跑几十分钟，提交必须立刻返回，不能等执行完。"""
    executor = make_executor(pool, space, log, token_chunk("好"))

    run = await executor.submit(thread_id=THREAD, content="算个波动率")

    assert run.status is RunStatus.QUEUED
    await executor.wait(run.id)


async def test_each_run_gets_its_own_id(pool: FakePool, space: FakeWorkspace, log: EventLog) -> None:
    executor = make_executor(pool, space, log)

    first = await executor.submit(thread_id=THREAD, content="一")
    second = await executor.submit(thread_id=THREAD, content="二")

    assert first.id != second.id
    await executor.aclose()


async def test_a_finished_run_is_queryable_by_id(pool: FakePool, space: FakeWorkspace, log: EventLog) -> None:
    executor = make_executor(pool, space, log)

    run = await executor.submit(thread_id=THREAD, content="一")
    await executor.wait(run.id)

    found = await executor.get(run.id)
    assert found is not None
    assert found.status is RunStatus.SUCCEEDED


async def test_an_unknown_run_is_not_found(pool: FakePool, space: FakeWorkspace, log: EventLog) -> None:
    executor = make_executor(pool, space, log)

    assert await executor.get("never-existed") is None


# ------------------------------------------------------------------ 事件序列
async def test_the_event_sequence_brackets_the_agent_output(
    pool: FakePool, space: FakeWorkspace, log: EventLog
) -> None:
    executor = make_executor(pool, space, log, token_chunk("好"), token_chunk("的"))

    run = await executor.submit(thread_id=THREAD, content="一")
    await executor.wait(run.id)

    assert types_of(log, run.id) == ["run.started", "sandbox.ready", "token", "token", "run.finished"]


async def test_run_started_carries_the_thread(pool: FakePool, space: FakeWorkspace, log: EventLog) -> None:
    executor = make_executor(pool, space, log)

    run = await executor.submit(thread_id=THREAD, content="一")
    await executor.wait(run.id)

    started = log.read(run.id)[0].event
    assert started.data.thread_id == THREAD  # type: ignore[union-attr]


async def test_every_event_carries_the_run_id(pool: FakePool, space: FakeWorkspace, log: EventLog) -> None:
    """前端可能同时订阅多个 run，信封里没有 run_id 就没法路由。"""
    executor = make_executor(pool, space, log, token_chunk("好"))

    run = await executor.submit(thread_id=THREAD, content="一")
    await executor.wait(run.id)

    assert {one.event.run_id for one in log.read(run.id)} == {run.id}


async def test_event_ids_increase_monotonically_across_the_whole_run(
    pool: FakePool, space: FakeWorkspace, log: EventLog
) -> None:
    executor = make_executor(pool, space, log, *[token_chunk(str(index)) for index in range(30)])

    run = await executor.submit(thread_id=THREAD, content="一")
    await executor.wait(run.id)

    ids = [one.id for one in log.read(run.id)]
    assert ids == sorted(ids, key=lambda one: tuple(int(part) for part in one.split("-")))


async def test_events_of_two_concurrent_runs_do_not_mix(pool: FakePool, space: FakeWorkspace, log: EventLog) -> None:
    executor = make_executor(pool, space, log, token_chunk("好"))

    first = await executor.submit(thread_id="thread-1", content="一")
    second = await executor.submit(thread_id="thread-2", content="二")
    await executor.wait(first.id)
    await executor.wait(second.id)

    assert types_of(log, first.id) == types_of(log, second.id)
    assert types_of(log, first.id) == ["run.started", "sandbox.ready", "token", "run.finished"]


# ------------------------------------------------------------------ token 计量
async def test_run_finished_accumulates_the_tokens_across_model_calls(
    pool: FakePool, space: FakeWorkspace, log: EventLog
) -> None:
    executor = make_executor(pool, space, log, usage_chunk(2916, 120), usage_chunk(4100, 80))

    run = await executor.submit(thread_id=THREAD, content="一")
    await executor.wait(run.id)

    assert tokens_of(log, run.id) == TokenUsage(input_cache_read=0, input_uncached=2916 + 4100, output=120 + 80)


async def test_cache_hits_are_reported_apart_from_the_rest(pool: FakePool, space: FakeWorkspace, log: EventLog) -> None:
    """§6.4：按 input 总数记会高估成本约 1.6 倍，两部分单价差得远，不能合并。"""
    executor = make_executor(pool, space, log, usage_chunk(304640, 8701, cache_read=189312))

    run = await executor.submit(thread_id=THREAD, content="一")
    await executor.wait(run.id)

    assert tokens_of(log, run.id) == TokenUsage(
        input_cache_read=189312,
        input_uncached=304640 - 189312,
        output=8701,
    )


async def test_a_missing_cache_detail_counts_as_no_hit(pool: FakePool, space: FakeWorkspace, log: EventLog) -> None:
    """换个不带 prompt cache 的模型时 `input_token_details` 整个不存在，不能因此崩掉。"""
    message = AIMessage(content="", usage_metadata={"input_tokens": 100, "output_tokens": 7, "total_tokens": 107})
    executor = make_executor(pool, space, log, ((), "updates", {"model": {"messages": [message]}}))

    run = await executor.submit(thread_id=THREAD, content="一")
    await executor.wait(run.id)

    assert tokens_of(log, run.id) == TokenUsage(input_cache_read=0, input_uncached=100, output=7)


async def test_tokens_are_zero_when_the_model_reports_no_usage(
    pool: FakePool, space: FakeWorkspace, log: EventLog
) -> None:
    executor = make_executor(pool, space, log, token_chunk("好"))

    run = await executor.submit(thread_id=THREAD, content="一")
    await executor.wait(run.id)

    assert tokens_of(log, run.id) == TokenUsage()


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

    executor = RunExecutor(pool=pool, workspace=space, log=log, runner=noisy, repository=FakeRepository())
    run = await executor.submit(thread_id=THREAD, content="一")
    try:
        await executor.wait(run.id)
    finally:
        probe.removeHandler(handler)

    line = json.loads(sink.getvalue())
    assert line["run_id"] == run.id
    assert line["thread_id"] == THREAD


# ------------------------------------------------------------------ 沙箱
async def test_the_sandbox_is_released_after_the_run(pool: FakePool, space: FakeWorkspace, log: EventLog) -> None:
    executor = make_executor(pool, space, log)

    run = await executor.submit(thread_id=THREAD, content="一")
    await executor.wait(run.id)

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

    executor = RunExecutor(pool=pool, workspace=space, log=log, runner=exploding, repository=FakeRepository())

    run = await executor.submit(thread_id=THREAD, content="一")
    await executor.wait(run.id)

    assert pool.released == [THREAD]


async def test_queue_positions_are_emitted_as_events(pool: FakePool, space: FakeWorkspace, log: EventLog) -> None:
    pool.queue_position = [3, 2, 1]
    executor = make_executor(pool, space, log)

    run = await executor.submit(thread_id=THREAD, content="一")
    await executor.wait(run.id)

    queued = [one.event for one in log.read(run.id) if one.event.type is EventType.SANDBOX_QUEUED]
    assert [one.data.position for one in queued] == [3, 2, 1]
    assert types_of(log, run.id)[:5] == [
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
    executor = make_executor(pool, space, log)

    run = await executor.submit(thread_id=THREAD, content="一")
    await executor.wait(run.id)

    failed = log.read(run.id)[-1].event
    assert failed.type is EventType.RUN_FAILED
    assert failed.data.code is RunErrorCode.SANDBOX_QUEUE_TIMEOUT
    assert failed.data.retryable is True
    assert (await executor.get(run.id)).status is RunStatus.FAILED  # type: ignore[union-attr]


async def test_a_failed_sandbox_acquisition_is_not_released(
    pool: FakePool, space: FakeWorkspace, log: EventLog
) -> None:
    pool.fail_with = SandboxQueueTimeoutError("等待沙箱超过 600 秒")
    executor = make_executor(pool, space, log)

    run = await executor.submit(thread_id=THREAD, content="一")
    await executor.wait(run.id)

    assert pool.released == []


# ------------------------------------------------------------------ 失败
async def test_an_agent_error_ends_the_run_as_failed(pool: FakePool, space: FakeWorkspace, log: EventLog) -> None:
    def exploding(backend: BackendProtocol, thread_id: str, content: str) -> AsyncIterator[StreamChunk]:
        async def stream() -> AsyncIterator[StreamChunk]:
            yield token_chunk("刚开了个头")
            raise RuntimeError("模型连接断了")

        return stream()

    executor = RunExecutor(pool=pool, workspace=space, log=log, runner=exploding, repository=FakeRepository())

    run = await executor.submit(thread_id=THREAD, content="一")
    await executor.wait(run.id)

    assert types_of(log, run.id) == ["run.started", "sandbox.ready", "token", "run.failed"]
    assert (await executor.get(run.id)).status is RunStatus.FAILED  # type: ignore[union-attr]


async def test_an_unclassified_error_is_not_retryable(pool: FakePool, space: FakeWorkspace, log: EventLog) -> None:
    """未分类异常按永久错误处理，盲目重试只会再炸一次还多花一份 token。"""

    def exploding(backend: BackendProtocol, thread_id: str, content: str) -> AsyncIterator[StreamChunk]:
        async def stream() -> AsyncIterator[StreamChunk]:
            raise RuntimeError("谁知道呢")
            yield  # pragma: no cover - 让函数成为异步生成器

        return stream()

    executor = RunExecutor(pool=pool, workspace=space, log=log, runner=exploding, repository=FakeRepository())

    run = await executor.submit(thread_id=THREAD, content="一")
    await executor.wait(run.id)

    failed = log.read(run.id)[-1].event
    assert failed.data.code is RunErrorCode.INTERNAL  # type: ignore[union-attr]
    assert failed.data.retryable is False  # type: ignore[union-attr]


async def test_a_failing_run_always_gets_a_terminal_event(pool: FakePool, space: FakeWorkspace, log: EventLog) -> None:
    """没有终态事件，订阅这个 run 的 SSE 连接会永远挂着。"""
    pool.fail_with = OSError("workspace 所在磁盘不可用")
    executor = make_executor(pool, space, log)

    run = await executor.submit(thread_id=THREAD, content="一")
    await executor.wait(run.id)

    assert types_of(log, run.id)[-1] == "run.failed"


# ------------------------------------------------------------------ 与事件流的衔接
async def test_a_follower_sees_the_whole_run_from_start_to_finish(
    pool: FakePool, space: FakeWorkspace, log: EventLog
) -> None:
    """步骤四的 SSE 端点就是这么用的：订阅先于事件产生。"""
    executor = make_executor(pool, space, log, token_chunk("好"), token_chunk("的"))
    run = await executor.submit(thread_id=THREAD, content="一")

    received = [one.event.model_dump()["type"] async for one in log.follow(run.id)]
    await executor.wait(run.id)

    assert received == ["run.started", "sandbox.ready", "token", "token", "run.finished"]


# ------------------------------------------------------------------ 关闭
async def test_closing_waits_for_running_tasks(pool: FakePool, space: FakeWorkspace, log: EventLog) -> None:
    executor = make_executor(pool, space, log, token_chunk("好"))
    run = await executor.submit(thread_id=THREAD, content="一")

    await executor.aclose()

    assert types_of(log, run.id)[-1] == "run.finished"


# ------------------------------------------------------------------ 产物
# 「哪些文件算产物」的判定在 broker 侧（见 test/broker/），这里只验执行器有没有
# 在正确的时间点去问、以及有没有把答案原样放进 run.finished。
async def test_run_finished_lists_what_this_run_produced(pool: FakePool, space: FakeWorkspace, log: EventLog) -> None:
    """产物端点靠这些标识拼 URL，不给的话教师只能从答复文本里猜路径。"""
    space.produced[THREAD] = [f"{THREAD}/chart.png"]
    executor = make_executor(pool, space, log, token_chunk("画好了"))

    run = await executor.submit(thread_id=THREAD, content="画个图")
    await executor.wait(run.id)

    assert artifacts_of(log, run.id) == [f"{THREAD}/chart.png"]


async def test_a_run_that_produced_nothing_reports_an_empty_list(
    pool: FakePool, space: FakeWorkspace, log: EventLog
) -> None:
    executor = make_executor(pool, space, log, token_chunk("说明一下就好"))

    run = await executor.submit(thread_id=THREAD, content="解释一下")
    await executor.wait(run.id)

    assert artifacts_of(log, run.id) == []


async def test_artifacts_are_asked_for_from_before_the_agent_started(
    pool: FakePool, space: FakeWorkspace, log: EventLog
) -> None:
    """基准晚于 agent 动手的话，本轮自己的产出会被判成「上一轮的」而漏掉。"""
    before = time.time_ns()
    executor = make_executor(pool, space, log, token_chunk("好"))

    run = await executor.submit(thread_id=THREAD, content="一")
    await executor.wait(run.id)

    asked_thread, asked_since = space.asked[0]
    assert asked_thread == THREAD
    assert before <= asked_since <= time.time_ns()
