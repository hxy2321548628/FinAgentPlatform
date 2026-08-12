"""用量报表的测试，连真库。

**聚合是这一步唯一的风险**：数字算错了不会报错，看板照样显示得漂漂亮亮 ——
成本可见性做成了成本误导。因此这里全部拿真的 `runs` 行去对数，不用替身。
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from event.model import TokenUsage
from report.usage import UsageReport, UserUsage
from run.repository import RunRepository
from test.conftest import FAKE_HASH
from thread.repository import Thread, ThreadRepository
from user.model import UserRole
from user.repository import User, UserRepository

# 报表窗口的参照时刻。写死而不用 now()，否则用例会在跨天的那一刻莫名其妙地红
NOW = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)
DAY = timedelta(days=1)
HOUR = timedelta(hours=1)


@pytest.fixture
def report(live_engine: AsyncEngine) -> UsageReport:
    return UsageReport(live_engine)


async def a_user(engine: AsyncEngine, role: UserRole = UserRole.TEACHER) -> User:
    return await UserRepository(engine).create(name=f"u-{uuid4().hex[:8]}", password_hash=FAKE_HASH, role=role)


async def _backdate(engine: AsyncEngine, run_id: str, started_at: datetime) -> None:
    """把 `started_at` 挪到过去。仓储不提供这个 —— 只有测试需要造历史。"""
    async with engine.begin() as connection:
        await connection.execute(
            text("UPDATE runs SET started_at = :at WHERE id = :id"), {"at": started_at, "id": run_id}
        )


async def a_run(engine: AsyncEngine, owner: User, thread: Thread, *, tokens: TokenUsage, at: datetime) -> str:
    """造一条已经跑完的 run，并把它的开始时间挪到指定时刻。"""
    repository = RunRepository(engine)
    run_id = uuid4().hex
    await repository.create(run_id=run_id, thread_id=thread.id, user_id=owner.id)
    await repository.start(run_id)
    await repository.succeed(run_id, tokens=tokens)
    await _backdate(engine, run_id, at)
    return run_id


async def mine(report: UsageReport, owner: User, *, since: datetime = NOW - DAY, until: datetime = NOW) -> UserUsage:
    """报表里属于这个人的那一行。"""
    return next(one for one in await report.by_user(since=since, until=until) if one.user_id == owner.id)


async def test_a_users_tokens_are_summed(
    report: UsageReport, live_engine: AsyncEngine, owner: User, owned_thread: Thread
) -> None:
    await a_run(
        live_engine,
        owner,
        owned_thread,
        tokens=TokenUsage(input_cache_read=100, input_uncached=20, output=3),
        at=NOW - HOUR,
    )
    await a_run(
        live_engine,
        owner,
        owned_thread,
        tokens=TokenUsage(input_cache_read=5, input_uncached=7, output=1),
        at=NOW - 2 * HOUR,
    )

    found = await mine(report, owner)

    assert (found.cache_read, found.uncached, found.output, found.runs) == (105, 27, 4, 2)


async def test_the_name_and_role_come_along(
    report: UsageReport, live_engine: AsyncEngine, owner: User, owned_thread: Thread
) -> None:
    """「谁花了多少」里的「谁」要能读 —— 一列 uuid 回答不了这个问题。"""
    await a_run(live_engine, owner, owned_thread, tokens=TokenUsage(input_uncached=1), at=NOW - HOUR)

    found = await mine(report, owner)

    assert found.name == owner.name
    assert found.role is UserRole.TEACHER


async def test_runs_outside_the_window_are_excluded(
    report: UsageReport, live_engine: AsyncEngine, owner: User, owned_thread: Thread
) -> None:
    """窗口错一天，账就算错一天 —— 而算错的账不会报错。"""
    await a_run(live_engine, owner, owned_thread, tokens=TokenUsage(input_uncached=999), at=NOW - 30 * DAY)
    await a_run(live_engine, owner, owned_thread, tokens=TokenUsage(input_uncached=7), at=NOW - HOUR)

    found = await mine(report, owner)

    assert (found.uncached, found.runs) == (7, 1)


async def test_two_users_are_reported_apart(
    report: UsageReport, live_engine: AsyncEngine, owner: User, owned_thread: Thread
) -> None:
    other = await a_user(live_engine)
    other_thread = await ThreadRepository(live_engine).create(user_id=other.id)
    await a_run(live_engine, owner, owned_thread, tokens=TokenUsage(input_uncached=10), at=NOW - HOUR)
    await a_run(live_engine, other, other_thread, tokens=TokenUsage(input_uncached=20), at=NOW - HOUR)

    found = {one.user_id: one.uncached for one in await report.by_user(since=NOW - DAY, until=NOW)}

    assert (found[owner.id], found[other.id]) == (10, 20)


async def test_the_heaviest_user_comes_first(
    report: UsageReport, live_engine: AsyncEngine, owner: User, owned_thread: Thread
) -> None:
    """看板要回答的是「谁花得最多」，排序就该是答案本身，而不是让人自己去找。"""
    light = await a_user(live_engine)
    light_thread = await ThreadRepository(live_engine).create(user_id=light.id)
    await a_run(live_engine, owner, owned_thread, tokens=TokenUsage(input_uncached=100), at=NOW - HOUR)
    await a_run(live_engine, light, light_thread, tokens=TokenUsage(input_uncached=1), at=NOW - HOUR)

    found = [one.user_id for one in await report.by_user(since=NOW - DAY, until=NOW)]

    assert found.index(owner.id) < found.index(light.id)


async def test_daily_buckets_split_by_day(
    report: UsageReport, live_engine: AsyncEngine, owner: User, owned_thread: Thread
) -> None:
    """「按时间聚合」的那一半。一天一个桶，看得出趋势。

    **断言的是增量而不是绝对值**：`by_day` 跨所有用户聚合，而测试库是整包用例共用的 ——
    别的用例留下的行照样落在同一个桶里。写死绝对值的话这条会随「今天已经跑过几条用例」
    时红时绿，而红的时候看不出是聚合坏了还是被别人的数据顶了。
    """
    before = {one.day: one.uncached for one in await report.by_day(since=NOW - 3 * DAY, until=NOW)}
    await a_run(live_engine, owner, owned_thread, tokens=TokenUsage(input_uncached=10), at=NOW - DAY)
    await a_run(live_engine, owner, owned_thread, tokens=TokenUsage(input_uncached=20), at=NOW - HOUR)

    after = {one.day: one.uncached for one in await report.by_day(since=NOW - 3 * DAY, until=NOW)}

    assert after[(NOW - DAY).date()] - before.get((NOW - DAY).date(), 0) == 10
    assert after[NOW.date()] - before.get(NOW.date(), 0) == 20


async def test_an_empty_window_reports_nothing(report: UsageReport) -> None:
    """没有用量不是错误，是「这段时间没人用」。"""
    far = datetime(2020, 1, 1, tzinfo=UTC)

    assert await report.by_user(since=far, until=far + DAY) == []
    assert await report.by_day(since=far, until=far + DAY) == []


async def test_a_run_that_did_not_succeed_still_counts_its_tokens(
    report: UsageReport, live_engine: AsyncEngine, owner: User, owned_thread: Thread
) -> None:
    """失败与取消的 run 也烧了 token，账要算进去 —— 只算成功的会低估真实成本。"""
    repository = RunRepository(live_engine)
    run_id = uuid4().hex
    await repository.create(run_id=run_id, thread_id=owned_thread.id, user_id=owner.id)
    await repository.start(run_id)
    await repository.cancel(run_id, tokens=TokenUsage(input_uncached=42))
    await _backdate(live_engine, run_id, NOW - HOUR)

    assert (await mine(report, owner)).uncached == 42
