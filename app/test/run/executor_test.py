"""执行器的测试，用假 agent 与假沙箱池 —— 一律不打真实模型 API。"""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from deepagents.backends.protocol import BackendProtocol
from langchain_core.messages import AIMessage, AIMessageChunk

from event.mapper import StreamChunk
from event.model import EventType, RunErrorCode, RunStatus
from run.executor import RunExecutor
from run.log import EventLog
from sandbox.container import CommandResult
from sandbox.pool import QueuePositionCallback, SandboxQueueTimeoutError

THREAD = "thread-1"


class FakeContainer:
    @property
    def id(self) -> str:
        return "fake-container"

    def exec(self, command: str, *, timeout: int) -> CommandResult:
        return CommandResult(output="", exit_code=0)


class FakePool:
    """记录借还次数的假池，可以被要求排队或直接超时。"""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.acquired: list[str] = []
        self.released: list[str] = []
        self.queue_position: list[int] = []
        self.fail_with: Exception | None = None

    def workspace_for(self, thread_id: str) -> Path:
        workspace = self.root / thread_id
        workspace.mkdir(parents=True, exist_ok=True)
        return workspace

    async def acquire(self, thread_id: str, *, on_queued: QueuePositionCallback | None = None) -> FakeContainer:
        for position in self.queue_position:
            if on_queued is not None:
                on_queued(position)
        if self.fail_with is not None:
            raise self.fail_with
        self.acquired.append(thread_id)
        return FakeContainer()

    async def release(self, thread_id: str) -> None:
        self.released.append(thread_id)


def chunk_stream(*chunk: StreamChunk) -> AsyncIterator[StreamChunk]:
    async def stream() -> AsyncIterator[StreamChunk]:
        for one in chunk:
            await asyncio.sleep(0)
            yield one

    return stream()


def token_chunk(text: str) -> StreamChunk:
    return ((), "messages", (AIMessageChunk(content=text), {}))


def usage_chunk(input_token: int, output_token: int) -> StreamChunk:
    message = AIMessage(
        content="",
        usage_metadata={"input_tokens": input_token, "output_tokens": output_token, "total_tokens": 0},
    )
    return ((), "updates", {"model": {"messages": [message]}})


@pytest.fixture
def pool(tmp_path: Path) -> FakePool:
    return FakePool(tmp_path)


@pytest.fixture
def log() -> EventLog:
    return EventLog()


def make_executor(pool: FakePool, log: EventLog, *chunk: StreamChunk) -> RunExecutor:
    def runner(backend: BackendProtocol, thread_id: str, content: str) -> AsyncIterator[StreamChunk]:
        return chunk_stream(*chunk)

    return RunExecutor(pool=pool, log=log, runner=runner)


def types_of(log: EventLog, run_id: str) -> list[str]:
    return [one.event.model_dump()["type"] for one in log.read(run_id)]


# ------------------------------------------------------------------ 提交
async def test_submit_returns_immediately_with_a_queued_run(pool: FakePool, log: EventLog) -> None:
    """任务要跑几十分钟，提交必须立刻返回，不能等执行完。"""
    executor = make_executor(pool, log, token_chunk("好"))

    run = await executor.submit(thread_id=THREAD, content="算个波动率")

    assert run.status is RunStatus.QUEUED
    await executor.wait(run.id)


async def test_each_run_gets_its_own_id(pool: FakePool, log: EventLog) -> None:
    executor = make_executor(pool, log)

    first = await executor.submit(thread_id=THREAD, content="一")
    second = await executor.submit(thread_id=THREAD, content="二")

    assert first.id != second.id
    await executor.aclose()


async def test_a_finished_run_is_queryable_by_id(pool: FakePool, log: EventLog) -> None:
    executor = make_executor(pool, log)

    run = await executor.submit(thread_id=THREAD, content="一")
    await executor.wait(run.id)

    found = executor.get(run.id)
    assert found is not None
    assert found.status is RunStatus.SUCCEEDED


def test_an_unknown_run_is_not_found(pool: FakePool, log: EventLog) -> None:
    executor = make_executor(pool, log)

    assert executor.get("never-existed") is None


# ------------------------------------------------------------------ 事件序列
async def test_the_event_sequence_brackets_the_agent_output(pool: FakePool, log: EventLog) -> None:
    executor = make_executor(pool, log, token_chunk("好"), token_chunk("的"))

    run = await executor.submit(thread_id=THREAD, content="一")
    await executor.wait(run.id)

    assert types_of(log, run.id) == ["run.started", "sandbox.ready", "token", "token", "run.finished"]


async def test_run_started_carries_the_thread(pool: FakePool, log: EventLog) -> None:
    executor = make_executor(pool, log)

    run = await executor.submit(thread_id=THREAD, content="一")
    await executor.wait(run.id)

    started = log.read(run.id)[0].event
    assert started.data.thread_id == THREAD  # type: ignore[union-attr]


async def test_every_event_carries_the_run_id(pool: FakePool, log: EventLog) -> None:
    """前端可能同时订阅多个 run，信封里没有 run_id 就没法路由。"""
    executor = make_executor(pool, log, token_chunk("好"))

    run = await executor.submit(thread_id=THREAD, content="一")
    await executor.wait(run.id)

    assert {one.event.run_id for one in log.read(run.id)} == {run.id}


async def test_event_ids_increase_monotonically_across_the_whole_run(pool: FakePool, log: EventLog) -> None:
    executor = make_executor(pool, log, *[token_chunk(str(index)) for index in range(30)])

    run = await executor.submit(thread_id=THREAD, content="一")
    await executor.wait(run.id)

    ids = [one.id for one in log.read(run.id)]
    assert ids == sorted(ids, key=lambda one: tuple(int(part) for part in one.split("-")))


async def test_events_of_two_concurrent_runs_do_not_mix(pool: FakePool, log: EventLog) -> None:
    executor = make_executor(pool, log, token_chunk("好"))

    first = await executor.submit(thread_id="thread-1", content="一")
    second = await executor.submit(thread_id="thread-2", content="二")
    await executor.wait(first.id)
    await executor.wait(second.id)

    assert types_of(log, first.id) == types_of(log, second.id)
    assert types_of(log, first.id) == ["run.started", "sandbox.ready", "token", "run.finished"]


# ------------------------------------------------------------------ token 计量
async def test_run_finished_reports_the_tokens_the_run_consumed(pool: FakePool, log: EventLog) -> None:
    executor = make_executor(pool, log, usage_chunk(2916, 120), usage_chunk(4100, 80))

    run = await executor.submit(thread_id=THREAD, content="一")
    await executor.wait(run.id)

    finished = log.read(run.id)[-1].event
    assert finished.data.tokens_used == 2916 + 120 + 4100 + 80  # type: ignore[union-attr]


async def test_tokens_are_zero_when_the_model_reports_no_usage(pool: FakePool, log: EventLog) -> None:
    executor = make_executor(pool, log, token_chunk("好"))

    run = await executor.submit(thread_id=THREAD, content="一")
    await executor.wait(run.id)

    finished = log.read(run.id)[-1].event
    assert finished.data.tokens_used == 0  # type: ignore[union-attr]


# ------------------------------------------------------------------ 沙箱
async def test_the_sandbox_is_released_after_the_run(pool: FakePool, log: EventLog) -> None:
    executor = make_executor(pool, log)

    run = await executor.submit(thread_id=THREAD, content="一")
    await executor.wait(run.id)

    assert pool.acquired == [THREAD]
    assert pool.released == [THREAD]


async def test_the_sandbox_is_released_even_when_the_agent_blows_up(pool: FakePool, log: EventLog) -> None:
    """不归还就是永久漏掉一个名额，几次之后整台机器就没有沙箱可用了。"""

    def exploding(backend: BackendProtocol, thread_id: str, content: str) -> AsyncIterator[StreamChunk]:
        async def stream() -> AsyncIterator[StreamChunk]:
            await asyncio.sleep(0)
            raise RuntimeError("模型连接断了")
            yield  # pragma: no cover - 让函数成为异步生成器

        return stream()

    executor = RunExecutor(pool=pool, log=log, runner=exploding)

    run = await executor.submit(thread_id=THREAD, content="一")
    await executor.wait(run.id)

    assert pool.released == [THREAD]


async def test_queue_positions_are_emitted_as_events(pool: FakePool, log: EventLog) -> None:
    pool.queue_position = [3, 2, 1]
    executor = make_executor(pool, log)

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


async def test_waiting_too_long_for_a_sandbox_fails_the_run_as_retryable(pool: FakePool, log: EventLog) -> None:
    """排队超时是资源不足，不是请求有问题 —— 过一会儿重试是有意义的。"""
    pool.fail_with = SandboxQueueTimeoutError("等待沙箱超过 600 秒")
    executor = make_executor(pool, log)

    run = await executor.submit(thread_id=THREAD, content="一")
    await executor.wait(run.id)

    failed = log.read(run.id)[-1].event
    assert failed.type is EventType.RUN_FAILED
    assert failed.data.code is RunErrorCode.SANDBOX_QUEUE_TIMEOUT
    assert failed.data.retryable is True
    assert executor.get(run.id).status is RunStatus.FAILED  # type: ignore[union-attr]


async def test_a_failed_sandbox_acquisition_is_not_released(pool: FakePool, log: EventLog) -> None:
    pool.fail_with = SandboxQueueTimeoutError("等待沙箱超过 600 秒")
    executor = make_executor(pool, log)

    run = await executor.submit(thread_id=THREAD, content="一")
    await executor.wait(run.id)

    assert pool.released == []


# ------------------------------------------------------------------ 失败
async def test_an_agent_error_ends_the_run_as_failed(pool: FakePool, log: EventLog) -> None:
    def exploding(backend: BackendProtocol, thread_id: str, content: str) -> AsyncIterator[StreamChunk]:
        async def stream() -> AsyncIterator[StreamChunk]:
            yield token_chunk("刚开了个头")
            raise RuntimeError("模型连接断了")

        return stream()

    executor = RunExecutor(pool=pool, log=log, runner=exploding)

    run = await executor.submit(thread_id=THREAD, content="一")
    await executor.wait(run.id)

    assert types_of(log, run.id) == ["run.started", "sandbox.ready", "token", "run.failed"]
    assert executor.get(run.id).status is RunStatus.FAILED  # type: ignore[union-attr]


async def test_an_unclassified_error_is_not_retryable(pool: FakePool, log: EventLog) -> None:
    """未分类异常按永久错误处理，盲目重试只会再炸一次还多花一份 token。"""

    def exploding(backend: BackendProtocol, thread_id: str, content: str) -> AsyncIterator[StreamChunk]:
        async def stream() -> AsyncIterator[StreamChunk]:
            raise RuntimeError("谁知道呢")
            yield  # pragma: no cover - 让函数成为异步生成器

        return stream()

    executor = RunExecutor(pool=pool, log=log, runner=exploding)

    run = await executor.submit(thread_id=THREAD, content="一")
    await executor.wait(run.id)

    failed = log.read(run.id)[-1].event
    assert failed.data.code is RunErrorCode.INTERNAL  # type: ignore[union-attr]
    assert failed.data.retryable is False  # type: ignore[union-attr]


async def test_a_failing_run_always_gets_a_terminal_event(pool: FakePool, log: EventLog) -> None:
    """没有终态事件，订阅这个 run 的 SSE 连接会永远挂着。"""
    pool.fail_with = OSError("workspace 所在磁盘不可用")
    executor = make_executor(pool, log)

    run = await executor.submit(thread_id=THREAD, content="一")
    await executor.wait(run.id)

    assert types_of(log, run.id)[-1] == "run.failed"


# ------------------------------------------------------------------ 与事件流的衔接
async def test_a_follower_sees_the_whole_run_from_start_to_finish(pool: FakePool, log: EventLog) -> None:
    """步骤四的 SSE 端点就是这么用的：订阅先于事件产生。"""
    executor = make_executor(pool, log, token_chunk("好"), token_chunk("的"))
    run = await executor.submit(thread_id=THREAD, content="一")

    received = [one.event.model_dump()["type"] async for one in log.follow(run.id)]
    await executor.wait(run.id)

    assert received == ["run.started", "sandbox.ready", "token", "token", "run.finished"]


# ------------------------------------------------------------------ 关闭
async def test_closing_waits_for_running_tasks(pool: FakePool, log: EventLog) -> None:
    executor = make_executor(pool, log, token_chunk("好"))
    run = await executor.submit(thread_id=THREAD, content="一")

    await executor.aclose()

    assert types_of(log, run.id)[-1] == "run.finished"
