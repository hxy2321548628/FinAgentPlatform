"""提交侧的测试：记一行 run，投一条任务。

**顺序是这里唯一要验的东西**：先落库再投递。反过来的话 worker 可能抢在 `runs` 行
写进去之前就开始改它的状态，而那一改会静默失败（仓储查不到行只记警告），
表现出来是「run 卡在 queued，事件却一路跑完了」。
"""

from uuid import uuid4

import pytest
from redis.asyncio import Redis

from event.model import RunStatus
from run.submitter import RunSubmitter
from task.queue import TaskQueue

CONSUMER = "submitter-test"


class RecordingRepository:
    """记下建过哪些行，并能在建行时回头看队列里有没有东西。"""

    def __init__(self, queue: TaskQueue) -> None:
        self._queue = queue
        self.created: list[tuple[str, str]] = []
        self.queued_when_created: list[int] = []

    async def create(self, *, run_id: str, thread_id: str) -> None:
        self.created.append((run_id, thread_id))
        self.queued_when_created.append(await self._queue.pending_count())


@pytest.fixture
async def queue(live_cache: Redis) -> TaskQueue:
    created = TaskQueue(live_cache, consumer=CONSUMER)
    await created.ensure_group()
    return created


async def test_submit_returns_a_queued_run(queue: TaskQueue) -> None:
    """任务要跑几十分钟，提交必须立刻返回，不能等执行完。"""
    submitter = RunSubmitter(repository=RecordingRepository(queue), queue=queue)

    run = await submitter.submit(thread_id=uuid4().hex, content="算个波动率")

    assert run.status is RunStatus.QUEUED
    assert run.id


async def test_each_run_gets_its_own_id(queue: TaskQueue) -> None:
    submitter = RunSubmitter(repository=RecordingRepository(queue), queue=queue)
    thread_id = uuid4().hex

    first = await submitter.submit(thread_id=thread_id, content="一")
    second = await submitter.submit(thread_id=thread_id, content="二")

    assert first.id != second.id


async def test_the_task_carries_everything_the_worker_needs(queue: TaskQueue) -> None:
    """少一个字段，worker 就得回头查库 —— 那正是拆进程之后最容易多出来的一次往返。"""
    submitter = RunSubmitter(repository=RecordingRepository(queue), queue=queue)
    thread_id = uuid4().hex

    run = await submitter.submit(thread_id=thread_id, content="算个波动率")

    delivery = await queue.reserve()
    assert delivery is not None
    assert delivery.task.run_id == run.id
    assert delivery.task.thread_id == thread_id
    assert delivery.task.content == "算个波动率"


async def test_the_row_is_written_before_the_task_is_published(queue: TaskQueue) -> None:
    """建行的那一刻队列里还不该有这条任务，否则 worker 可能先于它开跑。"""
    repository = RecordingRepository(queue)
    submitter = RunSubmitter(repository=repository, queue=queue)

    await submitter.submit(thread_id=uuid4().hex, content="一")

    assert repository.queued_when_created == [0]
