"""保留期清理的测试，连真 Postgres。

两条核心断言（步骤五的验证②）：**到点的真的被删掉**，以及**清理任务可以重跑**。
后一条不是形式主义 —— 它是 cron 任务，重试、补跑、手工再跑一次都会发生，
重跑一次多删一批的话，第二次执行就会把还在保留期内的数据带走。
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import CheckpointMetadata, empty_checkpoint
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from event.model import Event, TokenData, TokenEvent
from run.archive import EventArchive
from run.log import EventLog
from run.repository import RunRepository
from store.checkpoint import Checkpoint, open_checkpoint
from store.retention import purge, purge_checkpoint, purge_event
from test.conftest import TEST_POSTGRES_CONNINFO

NOW = datetime(2026, 8, 7, tzinfo=UTC)
RETENTION_DAY = 180


def _config(thread_id: str) -> RunnableConfig:
    return {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}


@pytest.fixture
async def live_checkpoint(live_engine: AsyncEngine) -> AsyncIterator[Checkpoint]:
    opened = await open_checkpoint(TEST_POSTGRES_CONNINFO)
    try:
        yield opened
    finally:
        await opened.aclose()


def token(text_value: str, run_id: str, *, ts: int) -> Event:
    return TokenEvent(ts=ts, run_id=run_id, path=(), data=TokenData(text=text_value))


def millisecond(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


@pytest.fixture
def archive(live_engine: AsyncEngine) -> EventArchive:
    return EventArchive(live_engine)


async def _write(log: EventLog, run_id: str, *, at: datetime) -> None:
    await log.append(token("一", run_id, ts=millisecond(at)))


async def _count(engine: AsyncEngine, run_id: str) -> int:
    async with engine.connect() as connection:
        result = await connection.execute(
            text("SELECT count(*) FROM run_events WHERE run_id = :run_id"),
            {"run_id": run_id},
        )
        return int(result.scalar_one())


# ------------------------------------------------------------------ 事件归档
async def test_events_past_the_retention_window_are_deleted(
    live_cache: Redis, archive: EventArchive, live_engine: AsyncEngine
) -> None:
    log = EventLog(live_cache, archive=archive)
    old = uuid4().hex
    await _write(log, old, at=NOW - timedelta(days=RETENTION_DAY + 1))

    await purge_event(live_engine, cutoff=NOW - timedelta(days=RETENTION_DAY))

    assert await _count(live_engine, old) == 0


async def test_events_inside_the_retention_window_are_kept(
    live_cache: Redis, archive: EventArchive, live_engine: AsyncEngine
) -> None:
    """删多了不会报错 —— 教师只是发现历史没了。这条是那一侧的护栏。"""
    log = EventLog(live_cache, archive=archive)
    recent = uuid4().hex
    await _write(log, recent, at=NOW - timedelta(days=RETENTION_DAY - 1))

    await purge_event(live_engine, cutoff=NOW - timedelta(days=RETENTION_DAY))

    assert await _count(live_engine, recent) == 1


async def test_purging_twice_removes_nothing_extra(
    live_cache: Redis, archive: EventArchive, live_engine: AsyncEngine
) -> None:
    """Cron 任务会被重试、补跑、手工再跑一次。第二次不能多删。"""
    log = EventLog(live_cache, archive=archive)
    recent = uuid4().hex
    await _write(log, recent, at=NOW - timedelta(days=1))
    cutoff = NOW - timedelta(days=RETENTION_DAY)

    await purge_event(live_engine, cutoff=cutoff)
    second = await purge_event(live_engine, cutoff=cutoff)

    assert second == 0
    assert await _count(live_engine, recent) == 1


async def test_purging_deletes_in_batches(live_cache: Redis, archive: EventArchive, live_engine: AsyncEngine) -> None:
    """一次删几百万行会锁住表、也会让 WAL 暴涨，所以要分批 —— 分批不能漏。"""
    log = EventLog(live_cache, archive=archive)
    old = uuid4().hex
    for index in range(5):
        await log.append(token(str(index), old, ts=millisecond(NOW - timedelta(days=RETENTION_DAY + 1))))

    removed = await purge_event(live_engine, cutoff=NOW - timedelta(days=RETENTION_DAY), batch=2)

    assert removed == 5
    assert await _count(live_engine, old) == 0


# ------------------------------------------------------------------ checkpoint
async def _seed_thread(engine: AsyncEngine, checkpoint: Checkpoint, *, last_active: datetime) -> str:
    """造一个有 checkpoint、且最后活动时间可指定的会话。"""
    thread_id = uuid4().hex
    await checkpoint.saver.aput(_config(thread_id), empty_checkpoint(), CheckpointMetadata(), {})
    run_id = uuid4().hex
    await RunRepository(engine).create(run_id=run_id, thread_id=thread_id)
    async with engine.begin() as connection:
        await connection.execute(
            text("UPDATE runs SET started_at = :moment WHERE id = :run_id"),
            {"moment": last_active, "run_id": run_id},
        )
    return thread_id


async def test_a_stale_thread_loses_its_checkpoints_but_an_active_one_does_not(
    live_engine: AsyncEngine, live_checkpoint: Checkpoint
) -> None:
    """判据是会话最后一次活动，不是 checkpoint 自己的时间 —— LangGraph 的表里没有时间列。

    两个会话一起验：只删掉旧的那条断言，靠「全删」也能满足。
    """
    stale = await _seed_thread(live_engine, live_checkpoint, last_active=NOW - timedelta(days=RETENTION_DAY + 1))
    active = await _seed_thread(live_engine, live_checkpoint, last_active=NOW - timedelta(days=1))

    await purge_checkpoint(live_engine, cutoff=NOW - timedelta(days=RETENTION_DAY))

    assert await live_checkpoint.saver.aget_tuple(_config(stale)) is None
    assert await live_checkpoint.saver.aget_tuple(_config(active)) is not None


# ------------------------------------------------------------------ 整体
async def test_purge_reports_what_it_removed(
    live_cache: Redis, archive: EventArchive, live_engine: AsyncEngine
) -> None:
    """跑完要说清删了多少 —— 静默的清理任务出问题时没人看得见。"""
    log = EventLog(live_cache, archive=archive)
    old = uuid4().hex
    await _write(log, old, at=NOW - timedelta(days=RETENTION_DAY + 1))

    removed, _ = await purge(live_engine, now=NOW, event_retention_day=RETENTION_DAY)

    assert removed >= 1
    assert await _count(live_engine, old) == 0
