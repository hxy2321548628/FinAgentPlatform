"""Worker 主循环的测试，连真 Redis。

验的是**领与 ack 的配合**：正常跑完要 ack，业务失败也要 ack（重投只会再失败一次，
还多花一份 token），而进程被打断留下的 pending 要能被另一个 worker 接走。
执行器本身在 test/run/executor_test.py 里验，这里的执行器是个只会记账的假货。
"""

import asyncio
from uuid import uuid4

import pytest
from redis.asyncio import Redis

from task.queue import RunTask, TaskQueue
from worker.loop import Worker

SHORT_BLOCK_MILLISECOND = 50
INSTANT_CLAIM_MILLISECOND = 0

# 主循环退出得等一轮阻塞走完，给足余量
STOP_TIMEOUT_SECOND = 5.0


def a_task(content: str = "一") -> RunTask:
    return RunTask(run_id=uuid4().hex, thread_id=uuid4().hex, content=content)


def make_queue(client: Redis, consumer: str, *, claim_idle_millisecond: int = 60_000) -> TaskQueue:
    return TaskQueue(
        client,
        consumer=consumer,
        block_millisecond=SHORT_BLOCK_MILLISECOND,
        claim_idle_millisecond=claim_idle_millisecond,
    )


class FakeExecutor:
    """只记账的执行器，可以被要求卡住或炸掉。"""

    def __init__(self) -> None:
        self.executed: list[str] = []
        self.blocker: asyncio.Event | None = None
        self.side_effect: Exception | None = None

    async def execute(self, task: RunTask) -> None:
        self.executed.append(task.run_id)
        if self.blocker is not None:
            await self.blocker.wait()
        if self.side_effect is not None:
            raise self.side_effect


@pytest.fixture
async def queue(live_cache: Redis) -> TaskQueue:
    created = make_queue(live_cache, "worker-a")
    await created.ensure_group()
    return created


async def _run_until(worker: Worker, done: asyncio.Event) -> None:
    """把 worker 跑起来，等条件满足后停掉它。"""
    running = asyncio.create_task(worker.run())
    try:
        await asyncio.wait_for(done.wait(), timeout=STOP_TIMEOUT_SECOND)
    finally:
        await worker.stop()
        await running


async def test_a_published_task_gets_executed(queue: TaskQueue) -> None:
    executor = FakeExecutor()
    worker = Worker(queue=queue, executor=executor)
    task = a_task()
    await queue.publish(task)
    done = asyncio.Event()

    async def watch() -> None:
        while not executor.executed:
            await asyncio.sleep(0)
        done.set()

    watcher = asyncio.create_task(watch())
    await _run_until(worker, done)
    await watcher

    assert executor.executed == [task.run_id]


async def test_a_finished_task_is_acked(queue: TaskQueue) -> None:
    """不 ack 的话它会一直占着 pending，最后被别的 worker 当成崩溃遗留重跑一遍。"""
    executor = FakeExecutor()
    worker = Worker(queue=queue, executor=executor)
    await queue.publish(a_task())
    done = asyncio.Event()

    async def watch() -> None:
        while executor.executed == []:
            await asyncio.sleep(0)
        done.set()

    watcher = asyncio.create_task(watch())
    await _run_until(worker, done)
    await watcher

    assert await queue.pending_count() == 0


async def test_a_task_whose_execution_blew_up_is_still_acked(queue: TaskQueue) -> None:
    """业务失败已经写了 run.failed，重投它只会再失败一次，还多花一份 token。"""
    executor = FakeExecutor()
    executor.side_effect = RuntimeError("执行器不该抛，但真抛了也不能卡住队列")
    worker = Worker(queue=queue, executor=executor)
    await queue.publish(a_task())
    done = asyncio.Event()

    async def watch() -> None:
        while executor.executed == []:
            await asyncio.sleep(0)
        await asyncio.sleep(0)
        done.set()

    watcher = asyncio.create_task(watch())
    await _run_until(worker, done)
    await watcher

    assert await queue.pending_count() == 0


async def test_stopping_waits_for_the_running_task(queue: TaskQueue) -> None:
    """一次分析几十分钟，掐掉等于把已经烧掉的 token 扔了。"""
    executor = FakeExecutor()
    executor.blocker = asyncio.Event()
    worker = Worker(queue=queue, executor=executor)
    await queue.publish(a_task())
    running = asyncio.create_task(worker.run())
    while not executor.executed:
        await asyncio.sleep(0)

    stopping = asyncio.create_task(worker.stop())
    await asyncio.sleep(0.1)
    still_waiting = not stopping.done()
    executor.blocker.set()
    await asyncio.wait_for(stopping, timeout=STOP_TIMEOUT_SECOND)
    await running

    assert still_waiting
    assert await queue.pending_count() == 0


async def test_one_worker_drives_several_runs_at_once(queue: TaskQueue) -> None:
    """一次分析绝大部分时间在等模型和等沙箱，一个一个跑用不满一个进程。"""
    executor = FakeExecutor()
    executor.blocker = asyncio.Event()
    worker = Worker(queue=queue, executor=executor, concurrency=3)
    for index in range(3):
        await queue.publish(a_task(str(index)))
    running = asyncio.create_task(worker.run())

    while len(executor.executed) < 3:
        await asyncio.sleep(0)
    executor.blocker.set()
    await worker.stop()
    await running

    assert len(executor.executed) == 3


async def test_a_crashed_worker_leaves_its_task_for_the_next_one(live_cache: Redis) -> None:
    """验收标准①：kill -9 之后任务不能就此消失。

    这里用「领了但永远不 ack」来模拟被打断的进程 —— `kill -9` 留下的正是这个状态。
    """
    dead = make_queue(live_cache, "worker-dead")
    await dead.ensure_group()
    task = a_task()
    await dead.publish(task)
    await dead.reserve()

    alive_queue = make_queue(live_cache, "worker-alive", claim_idle_millisecond=INSTANT_CLAIM_MILLISECOND)
    executor = FakeExecutor()
    worker = Worker(queue=alive_queue, executor=executor)
    done = asyncio.Event()

    async def watch() -> None:
        while executor.executed == []:
            await asyncio.sleep(0)
        done.set()

    watcher = asyncio.create_task(watch())
    await _run_until(worker, done)
    await watcher

    assert executor.executed == [task.run_id]
