"""提交侧的测试：记一行 run，投一条任务。

**顺序是这里唯一要验的东西**：先落库再投递。反过来的话 worker 可能抢在 `runs` 行
写进去之前就开始改它的状态，而那一改会静默失败（仓储查不到行只记警告），
表现出来是「run 卡在 queued，事件却一路跑完了」。
"""

from uuid import uuid4

import pytest
from redis.asyncio import Redis

from app.agent.config import AgentConfig
from app.agent.user_context import UserContext
from app.event.model import RunStatus
from app.run.decision import Decision, DecisionType
from app.run.submitter import RunSubmitter
from app.task.queue import TaskQueue
from app.user.model import UserRole
from test.conftest import json_log

CONSUMER = "submitter-test"

SUBMITTER_LOGGER = "app.run.submitter"

# 提交侧不查库，因此这里只要一个形状对的标识
USER_ID = uuid4().hex


def a_user_context() -> UserContext:
    return UserContext(
        name="张老师",
        role=UserRole.TEACHER,
        dept="金融学院",
        token_used_today=123,
        token_limit_daily=50_000,
        active_runs=1,
        concurrent_run_limit=3,
    )


class RecordingRepository:
    """记下建过哪些行，并能在建行时回头看队列里有没有东西。"""

    def __init__(self, queue: TaskQueue) -> None:
        self._queue = queue
        self.created: list[tuple[str, str, str]] = []
        self.content: list[str | None] = []
        self.agent_config: list[dict[str, object] | None] = []
        self.user_context: list[dict[str, object] | None] = []
        self.queued_when_created: list[int] = []

    async def create(
        self,
        *,
        run_id: str,
        thread_id: str,
        user_id: str,
        content: str | None = None,
        agent_config: dict[str, object] | None = None,
        user_context: dict[str, object] | None = None,
    ) -> None:
        self.created.append((run_id, thread_id, user_id))
        self.content.append(content)
        self.agent_config.append(agent_config)
        self.user_context.append(user_context)
        self.queued_when_created.append(await self._queue.pending_count())


@pytest.fixture
async def queue(live_cache: Redis) -> TaskQueue:
    created = TaskQueue(live_cache, consumer=CONSUMER)
    await created.ensure_group()
    return created


async def test_submit_returns_a_queued_run(queue: TaskQueue) -> None:
    """任务要跑几十分钟，提交必须立刻返回，不能等执行完。"""
    submitter = RunSubmitter(repository=RecordingRepository(queue), queue=queue)

    run = await submitter.submit(
        thread_id=uuid4().hex, content="算个波动率", user_id=USER_ID, agent_config=AgentConfig()
    )

    assert run.status is RunStatus.QUEUED
    assert run.id


async def test_each_run_gets_its_own_id(queue: TaskQueue) -> None:
    submitter = RunSubmitter(repository=RecordingRepository(queue), queue=queue)
    thread_id = uuid4().hex

    first = await submitter.submit(thread_id=thread_id, content="一", user_id=USER_ID, agent_config=AgentConfig())
    second = await submitter.submit(thread_id=thread_id, content="二", user_id=USER_ID, agent_config=AgentConfig())

    assert first.id != second.id


async def test_the_task_carries_everything_the_worker_needs(queue: TaskQueue) -> None:
    """少一个字段，worker 就得回头查库 —— 那正是拆进程之后最容易多出来的一次往返。"""
    submitter = RunSubmitter(repository=RecordingRepository(queue), queue=queue)
    thread_id = uuid4().hex

    run = await submitter.submit(thread_id=thread_id, content="算个波动率", user_id=USER_ID, agent_config=AgentConfig())

    delivery = await queue.reserve()
    assert delivery is not None
    assert delivery.task.run_id == run.id
    assert delivery.task.thread_id == thread_id
    assert delivery.task.content == "算个波动率"
    assert delivery.task.agent_config == AgentConfig()


async def test_the_question_is_written_down_as_well_as_queued(queue: TaskQueue) -> None:
    """队列那份跑完就没了。库里这份是聊天历史的用户那一侧 —— 少了它就只剩 agent 的独白。"""
    repository = RecordingRepository(queue)
    submitter = RunSubmitter(repository=repository, queue=queue)

    await submitter.submit(
        thread_id=uuid4().hex, content="按行业分组算年化波动率", user_id=USER_ID, agent_config=AgentConfig()
    )

    assert repository.content == ["按行业分组算年化波动率"]


async def test_the_row_is_written_before_the_task_is_published(queue: TaskQueue) -> None:
    """建行的那一刻队列里还不该有这条任务，否则 worker 可能先于它开跑。"""
    repository = RecordingRepository(queue)
    submitter = RunSubmitter(repository=repository, queue=queue)

    await submitter.submit(thread_id=uuid4().hex, content="一", user_id=USER_ID, agent_config=AgentConfig())

    assert repository.queued_when_created == [0]


async def test_the_snapshot_is_exactly_what_the_caller_handed_in(queue: TaskQueue) -> None:
    """这一层不做任何取舍。

    **会话默认与本轮覆盖怎么合、agent 引用怎么解析，都在端点那一层做完了。**
    提交侧多一处能改配置的地方，就多一种「快照与实际跑的不是同一份」的失效。
    """
    repository = RecordingRepository(queue)
    submitter = RunSubmitter(repository=repository, queue=queue)
    resolved = AgentConfig(system_prompt="每句以喵开头", agent_id=uuid4().hex, agent_version=1)

    run = await submitter.submit(
        thread_id=uuid4().hex,
        content="一",
        user_id=USER_ID,
        agent_config=resolved,
    )

    delivery = await queue.reserve()
    assert delivery is not None
    assert run.agent_config == resolved
    assert repository.agent_config == [resolved.model_dump(exclude_none=True)]
    assert delivery.task.agent_config == resolved


async def test_safe_user_context_is_frozen_in_row_and_task(queue: TaskQueue) -> None:
    repository = RecordingRepository(queue)
    submitter = RunSubmitter(repository=repository, queue=queue)
    context = a_user_context()

    run = await submitter.submit(
        thread_id=uuid4().hex,
        content="一",
        user_id=USER_ID,
        agent_config=AgentConfig(),
        user_context=context,
    )

    delivery = await queue.reserve()
    assert delivery is not None
    assert run.user_context == context
    assert delivery.task.user_context == context
    assert repository.user_context == [context.model_dump(mode="json")]
    serialized = str(repository.user_context[0])
    assert "email" not in serialized
    assert USER_ID not in serialized


async def test_an_unreferenced_run_carries_no_extra_key(queue: TaskQueue) -> None:
    """不选 agent 时快照里一个键都不多 —— 历史判据断言的正是「快照 == 当时那份配置」。"""
    repository = RecordingRepository(queue)
    submitter = RunSubmitter(repository=repository, queue=queue)

    await submitter.submit(thread_id=uuid4().hex, content="一", user_id=USER_ID, agent_config=AgentConfig())

    assert repository.agent_config == [{}]


async def test_an_approval_resubmission_carries_the_original_snapshot(queue: TaskQueue) -> None:
    submitter = RunSubmitter(repository=RecordingRepository(queue), queue=queue)
    config = AgentConfig(system_prompt="这是原 run 的快照")
    context = a_user_context()

    await submitter.resubmit(
        run_id=uuid4().hex,
        thread_id=uuid4().hex,
        user_id=USER_ID,
        decisions=[Decision(index=0, type=DecisionType.APPROVE)],
        agent_config=config,
        user_context=context,
    )

    delivery = await queue.reserve()
    assert delivery is not None
    assert delivery.task.agent_config == config
    assert delivery.task.user_context == context


async def test_the_submission_log_carries_the_run_identity(queue: TaskQueue) -> None:
    """执行搬到 worker 之后，api 进程里关于一个 run 就只剩这一段。

    这里不带 id 的话，「按 run_id 把一次 run 的日志过滤出来」在 api 侧就恒为空 ——
    教师报「提交了没反应」时，第一个要回答的「api 到底收没收到」也就查不了。
    """
    submitter = RunSubmitter(repository=RecordingRepository(queue), queue=queue)
    thread_id = uuid4().hex

    with json_log(SUBMITTER_LOGGER) as line:
        run = await submitter.submit(
            thread_id=thread_id, content="算个波动率", user_id=USER_ID, agent_config=AgentConfig()
        )

    assert [(one.get("run_id"), one.get("thread_id"), one.get("user_id")) for one in line] == [
        (run.id, thread_id, USER_ID)
    ]
