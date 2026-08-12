"""待审批的堆积计数与超时清扫，连真 Postgres。"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from event.model import EventType, RunStatus, TokenUsage
from run.approval import DEFAULT_TIMEOUT_HOUR, expired, pending_count, sweep
from run.log import EventLog
from run.repository import RunRepository
from thread.repository import Thread
from user.repository import User

NOW = datetime(2026, 8, 8, tzinfo=UTC)


@pytest.fixture
def repository(live_engine: AsyncEngine) -> RunRepository:
    return RunRepository(live_engine)


async def _waiting(engine: AsyncEngine, owner: User, thread: Thread, *, started: datetime | None = None) -> str:
    """造一个挂在等人确认上的 run，可以指定它是什么时候提交的。"""
    run_id = uuid4().hex
    repository = RunRepository(engine)
    await repository.create(run_id=run_id, thread_id=thread.id, user_id=owner.id)
    await repository.wait_approval(run_id, tokens=TokenUsage())
    if started is not None:
        # 「提交于 25 小时前」没有公开入口造得出来，只能直接改那一列
        async with engine.begin() as connection:
            await connection.execute(
                text("UPDATE runs SET started_at = :moment WHERE id = :run_id"),
                {"moment": started, "run_id": run_id},
            )
    return run_id


async def test_a_fresh_user_has_nothing_waiting(live_engine: AsyncEngine, owner: User) -> None:
    assert await pending_count(live_engine, owner.id) == 0


async def test_a_waiting_run_is_counted(
    live_engine: AsyncEngine, repository: RunRepository, owner: User, owned_thread: Thread
) -> None:
    await _waiting(live_engine, owner, owned_thread)

    assert await pending_count(live_engine, owner.id) == 1


async def test_another_users_waiting_runs_are_not_counted(
    live_engine: AsyncEngine, repository: RunRepository, owner: User, owned_thread: Thread
) -> None:
    await _waiting(live_engine, owner, owned_thread)

    assert await pending_count(live_engine, uuid4().hex) == 0


async def test_a_finished_run_stops_being_counted(
    live_engine: AsyncEngine, repository: RunRepository, owner: User, owned_thread: Thread
) -> None:
    run_id = await _waiting(live_engine, owner, owned_thread)
    await repository.resume(run_id)
    await repository.succeed(run_id, tokens=TokenUsage())

    assert await pending_count(live_engine, owner.id) == 0


# ------------------------------------------------------------------ 超时
async def test_a_recent_wait_is_not_expired(
    live_engine: AsyncEngine, repository: RunRepository, owner: User, owned_thread: Thread
) -> None:
    """教师可能下班后才看到，几小时太短 —— 这条是那一侧的护栏。"""
    run_id = await _waiting(live_engine, owner, owned_thread, started=NOW - timedelta(hours=DEFAULT_TIMEOUT_HOUR - 1))

    assert run_id not in await expired(live_engine, now=NOW)


async def test_a_long_wait_is_expired(
    live_engine: AsyncEngine, repository: RunRepository, owner: User, owned_thread: Thread
) -> None:
    run_id = await _waiting(live_engine, owner, owned_thread, started=NOW - timedelta(hours=DEFAULT_TIMEOUT_HOUR + 1))

    assert run_id in await expired(live_engine, now=NOW)


async def test_sweeping_turns_an_expired_wait_into_cancelled(
    live_engine: AsyncEngine, live_cache: Redis, repository: RunRepository, owner: User, owned_thread: Thread
) -> None:
    run_id = await _waiting(live_engine, owner, owned_thread, started=NOW - timedelta(hours=DEFAULT_TIMEOUT_HOUR + 1))
    log = EventLog(live_cache)

    swept = await sweep(live_engine, log, now=NOW)

    assert swept >= 1
    found = await repository.get(run_id, user_id=owner.id)
    assert found is not None
    assert found.status is RunStatus.CANCELLED


async def test_sweeping_pushes_run_cancelled(
    live_engine: AsyncEngine, live_cache: Redis, repository: RunRepository, owner: User, owned_thread: Thread
) -> None:
    """超时转取消对教师是「这次没跑成」，那条消息只能从事件流上得到。"""
    run_id = await _waiting(live_engine, owner, owned_thread, started=NOW - timedelta(hours=DEFAULT_TIMEOUT_HOUR + 1))
    log = EventLog(live_cache)

    await sweep(live_engine, log, now=NOW)

    assert [one.event.type for one in await log.read(run_id)] == [EventType.RUN_CANCELLED]


async def test_sweeping_twice_changes_nothing_extra(
    live_engine: AsyncEngine, live_cache: Redis, repository: RunRepository, owner: User, owned_thread: Thread
) -> None:
    """Cron 任务会被重试、补跑、手工再跑一次。第二次不该再推一条事件。"""
    run_id = await _waiting(live_engine, owner, owned_thread, started=NOW - timedelta(hours=DEFAULT_TIMEOUT_HOUR + 1))
    log = EventLog(live_cache)
    await sweep(live_engine, log, now=NOW)

    await sweep(live_engine, log, now=NOW)

    assert len(await log.read(run_id)) == 1
