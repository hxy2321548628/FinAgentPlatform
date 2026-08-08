"""平台指标的测试，连真库真 Redis。

**这一步最容易出的错是「指标有值但对不上」**：一条查询写错了范围、少了一个状态，
抓取端点照样 200，Grafana 上照样画得出线 —— 只是那条线不再是它标签说的东西。
因此这里每一条都拿真的 run 去对数，且**只断言增量**：库是整包用例共用的，
断绝对值等于断「别的用例没跑过」。
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from prometheus_client import CollectorRegistry
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from event.model import RunStatus, TokenUsage
from metric.platform import CACHE_READ_KIND, OUTPUT_KIND, UNCACHED_KIND, collect_platform
from report.usage import UsageReport, UserUsage
from run.repository import RunRepository
from task.queue import RunTask, TaskQueue
from test.conftest import FAKE_HASH
from thread.repository import ThreadRepository
from user.model import UserRole
from user.repository import User, UserRepository

RUN_METRIC = "zuel_run"
PENDING_METRIC = "zuel_task_pending"
TOKEN_METRIC = "zuel_token_today"

# 一次假分析的 token 三元组。三个数**互不相同**：写反了 kind 标签时才看得出来
TOKENS = TokenUsage(input_cache_read=101, input_uncached=202, output=303)

TEST_CONSUMER = "metric-test"

# 不连库的那两条用例用的参照时刻。取什么值都行 —— 假报表不看它
NOW = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)


class FakeCount:
    """按状态数 run，但数出来的是喂进去的那份。"""

    def __init__(self, counted: dict[RunStatus, int]) -> None:
        self._counted = counted

    async def live_count(self) -> dict[RunStatus, int]:
        return self._counted


class FakeDepth:
    async def pending_count(self) -> int:
        return 0


class FakeReport:
    async def by_user(self, *, since: datetime, until: datetime) -> list[UserUsage]:
        return []


@pytest.fixture
def repository(live_engine: AsyncEngine) -> RunRepository:
    return RunRepository(live_engine)


@pytest.fixture
def queue(live_cache: Redis) -> TaskQueue:
    return TaskQueue(live_cache, consumer=TEST_CONSUMER)


@pytest.fixture
def report(live_engine: AsyncEngine) -> UsageReport:
    return UsageReport(live_engine)


async def snapshot(repository: RunRepository, queue: TaskQueue, report: UsageReport) -> CollectorRegistry:
    return await collect_platform(runs=repository, queue=queue, report=report, now=datetime.now(UTC))


def run_gauge(registry: CollectorRegistry, status: RunStatus) -> float:
    value = registry.get_sample_value(RUN_METRIC, {"status": status.value})
    assert value is not None, f"{RUN_METRIC}{{status={status.value}}} 这条序列压根没出现"
    return value


def token_gauge(registry: CollectorRegistry, name: str, kind: str) -> float | None:
    return registry.get_sample_value(TOKEN_METRIC, {"user": name, "kind": kind})


async def a_queued_run(engine: AsyncEngine, owner: User) -> str:
    """造一条刚投进来、还没开跑的 run，返回它的 id。"""
    thread = await ThreadRepository(engine).create(user_id=owner.id, title="t")
    run_id = uuid4().hex
    await RunRepository(engine).create(run_id=run_id, thread_id=thread.id, user_id=owner.id)
    return run_id


async def test_a_queued_run_shows_up_as_backlog(
    live_engine: AsyncEngine, repository: RunRepository, queue: TaskQueue, report: UsageReport, owner: User
) -> None:
    """还没开跑的 run 是积压。**断增量**：库里本来就可能有别的用例留下的行。"""
    before = run_gauge(await snapshot(repository, queue, report), RunStatus.QUEUED)

    await a_queued_run(live_engine, owner)

    assert run_gauge(await snapshot(repository, queue, report), RunStatus.QUEUED) == before + 1


async def test_a_started_run_moves_from_queued_to_running(
    live_engine: AsyncEngine, repository: RunRepository, queue: TaskQueue, report: UsageReport, owner: User
) -> None:
    """状态一变，两条序列要同时动 —— 只加不减的话看板上会凭空多出一批 run。"""
    run_id = await a_queued_run(live_engine, owner)
    before = await snapshot(repository, queue, report)

    await repository.start(run_id)

    after = await snapshot(repository, queue, report)
    assert run_gauge(after, RunStatus.QUEUED) == run_gauge(before, RunStatus.QUEUED) - 1
    assert run_gauge(after, RunStatus.RUNNING) == run_gauge(before, RunStatus.RUNNING) + 1


async def test_a_finished_run_leaves_the_live_gauges(
    live_engine: AsyncEngine, repository: RunRepository, queue: TaskQueue, report: UsageReport, owner: User
) -> None:
    """终态的 run 不该再占任何一条活跃序列 —— 否则那几个数只会一直涨。"""
    run_id = await a_queued_run(live_engine, owner)
    await repository.start(run_id)
    before = await snapshot(repository, queue, report)

    await repository.succeed(run_id, tokens=TOKENS)

    assert run_gauge(await snapshot(repository, queue, report), RunStatus.RUNNING) == (
        run_gauge(before, RunStatus.RUNNING) - 1
    )


async def test_every_live_status_has_a_series_even_at_zero() -> None:
    """一个都没有的状态也要有一条值为 0 的序列。

    缺序列与「值是 0」在 PromQL 里是两回事：告警规则遇到缺失的序列是整条不成立，
    而不是不触发 —— 那正是「告警配了但永远不响」最常见的成因。

    **这一条不能连真库。** 整包用例共用一个库，三种状态多半都恰好有行躺着，
    于是「补零」这段代码删掉了它照样绿 —— 实测过，确实照样绿。
    """
    registry = await collect_platform(runs=FakeCount({}), queue=FakeDepth(), report=FakeReport(), now=NOW)

    for status in (RunStatus.QUEUED, RunStatus.RUNNING, RunStatus.WAITING_APPROVAL):
        assert registry.get_sample_value(RUN_METRIC, {"status": status.value}) == 0


async def test_a_terminal_status_is_not_reported_at_all() -> None:
    """终态不做成 gauge：那只会得到一条永远在涨的线，既报不了警也看不出趋势。

    同上，喂一个「连终态都数出来了」的假计数器 —— 真库里查不出这种结果，
    因此连着真库时这条断言恒真。
    """
    registry = await collect_platform(
        runs=FakeCount({RunStatus.SUCCEEDED: 7}), queue=FakeDepth(), report=FakeReport(), now=NOW
    )

    assert registry.get_sample_value(RUN_METRIC, {"status": RunStatus.SUCCEEDED.value}) is None


async def test_an_unacked_task_shows_up_as_queue_depth(
    repository: RunRepository, queue: TaskQueue, report: UsageReport
) -> None:
    """领了没 ack 的任务就是积压。

    **它与 `zuel_run{status="queued"}` 不是同一个数**，两者一起看才分得清
    「没人领」与「领了跑不完」。
    """
    await queue.ensure_group()
    before = (await snapshot(repository, queue, report)).get_sample_value(PENDING_METRIC)
    assert before is not None
    run_id = uuid4().hex
    await queue.publish(RunTask(run_id=run_id, thread_id="metric-thread", content="问题"))
    delivery = await queue.reserve()
    # 领到的不是刚投的那条，说明队列里还躺着别的用例的残留 —— 这时候下面的增量
    # 断言会红在「指标不动」上，而真因在队列。先把它说清楚
    assert delivery is not None and delivery.task.run_id == run_id

    try:
        taken = (await snapshot(repository, queue, report)).get_sample_value(PENDING_METRIC)
        assert taken == before + 1, f"领走一条之后积压该是 {before + 1}，实际 {taken}"
    finally:
        await queue.ack(delivery.id)

    assert (await snapshot(repository, queue, report)).get_sample_value(PENDING_METRIC) == before


async def test_today_token_is_reported_per_user_and_split_by_cache(
    live_engine: AsyncEngine, repository: RunRepository, queue: TaskQueue, report: UsageReport
) -> None:
    """谁烧了多少，且 cache 命中与否分开。

    三个数字刻意互不相同：把 kind 标签写反时，只有这样才看得出来。
    这里用的是本条用例自己新建的用户，因此可以断绝对值。
    """
    fresh = await UserRepository(live_engine).create(
        name=f"metric-{uuid4().hex[:8]}", password_hash=FAKE_HASH, role=UserRole.TEACHER
    )
    run_id = await a_queued_run(live_engine, fresh)
    await repository.start(run_id)
    await repository.succeed(run_id, tokens=TOKENS)

    registry = await snapshot(repository, queue, report)

    assert token_gauge(registry, fresh.name, CACHE_READ_KIND) == TOKENS.input_cache_read
    assert token_gauge(registry, fresh.name, UNCACHED_KIND) == TOKENS.input_uncached
    assert token_gauge(registry, fresh.name, OUTPUT_KIND) == TOKENS.output


async def test_a_user_with_no_run_today_has_no_series(
    live_engine: AsyncEngine, repository: RunRepository, queue: TaskQueue, report: UsageReport
) -> None:
    """今天没跑过的人不该出现。

    **补零是错的**：注册表每次抓取现建，补零意味着全校每个账号每 15 秒占三条序列，
    而其中绝大多数永远是 0。
    """
    idle = await UserRepository(live_engine).create(
        name=f"idle-{uuid4().hex[:8]}", password_hash=FAKE_HASH, role=UserRole.TEACHER
    )

    registry = await snapshot(repository, queue, report)

    assert token_gauge(registry, idle.name, UNCACHED_KIND) is None


async def test_the_process_itself_is_reported(repository: RunRepository, queue: TaskQueue, report: UsageReport) -> None:
    """进程自己的常驻内存也要在里面 —— 「api 为什么越来越胖」没有它只能靠 top 猜。"""
    registry = await snapshot(repository, queue, report)

    assert registry.get_sample_value("process_resident_memory_bytes") is not None
