"""memory job 仓储的重试与分项用量账测试。"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.event.model import TokenUsage
from app.memory.job import MemoryJobPayload, MemoryJobRepository, MemoryUsage, MemoryUsageStage
from app.run.repository import RunRepository
from app.thread.repository import Thread
from app.user.repository import User


async def test_claim_returns_materialized_job_after_committing_running_state(
    live_engine: AsyncEngine,
    owner: User,
    owned_thread: Thread,
) -> None:
    """提交会过期 ORM 实例，claim 仍须返回可直接使用的任务快照。"""
    run_id = uuid4().hex
    runs = RunRepository(live_engine)
    await runs.create(run_id=run_id, thread_id=owned_thread.id, user_id=owner.id)
    await runs.succeed(
        run_id,
        tokens=TokenUsage(),
        memory_job=MemoryJobPayload(
            thread_id=owned_thread.id,
            user_id=owner.id,
            messages=[{"role": "user", "content": "请记住偏好"}],
        ),
    )
    async with live_engine.begin() as connection:
        await connection.execute(
            text("UPDATE memory_jobs SET created_at = :created_at WHERE run_id = :run_id"),
            {"created_at": datetime(2000, 1, 1, tzinfo=UTC), "run_id": run_id},
        )

    claimed = await MemoryJobRepository(live_engine).claim()

    assert claimed is not None
    assert claimed.run_id == run_id
    assert claimed.thread_id == owned_thread.id
    assert claimed.user_id == owner.id
    assert claimed.messages == [{"role": "user", "content": "请记住偏好"}]
    assert claimed.attempts == 1


async def test_running_memory_job_can_be_requeued_with_a_sanitized_error(
    live_engine: AsyncEngine,
    owner: User,
    owned_thread: Thread,
) -> None:
    run_id = uuid4().hex
    runs = RunRepository(live_engine)
    await runs.create(run_id=run_id, thread_id=owned_thread.id, user_id=owner.id)
    await runs.succeed(
        run_id,
        tokens=TokenUsage(),
        memory_job=MemoryJobPayload(
            thread_id=owned_thread.id,
            user_id=owner.id,
            messages=[{"role": "user", "content": "请记住偏好"}],
        ),
    )
    async with live_engine.begin() as connection:
        found = await connection.execute(
            text("SELECT id FROM memory_jobs WHERE run_id = :run_id"),
            {"run_id": run_id},
        )
        job_id = str(found.scalar_one()).replace("-", "")
        await connection.execute(
            text("UPDATE memory_jobs SET status = 'running', attempts = 1, started_at = now() WHERE id = :id"),
            {"id": job_id},
        )

    assert await MemoryJobRepository(live_engine).requeue(job_id, error="extractor失败：TimeoutError") is True

    async with live_engine.connect() as connection:
        found = await connection.execute(
            text("SELECT status, started_at, last_error FROM memory_jobs WHERE id = :id"),
            {"id": job_id},
        )
        row = found.mappings().one()
    assert row["status"] == "queued"
    assert row["started_at"] is None
    assert row["last_error"] == "extractor失败：TimeoutError"


async def test_selector_usage_round_trips_selected_slugs(
    live_engine: AsyncEngine,
    owner: User,
    owned_thread: Thread,
) -> None:
    """选择证据属于持久化账本，不能只留在当次进程内存里。"""
    run_id = uuid4().hex
    await RunRepository(live_engine).create(run_id=run_id, thread_id=owned_thread.id, user_id=owner.id)
    repository = MemoryJobRepository(live_engine)

    await repository.record_usage(
        MemoryUsage(
            run_id=run_id,
            thread_id=owned_thread.id,
            stage=MemoryUsageStage.SELECTOR,
            model="selector-model",
            tokens=TokenUsage(input_uncached=7, output=2),
            cost_yuan=0.03,
            duration_ms=12,
            selected_slugs=("risk-preference", "project-rule"),
        )
    )

    found = await repository.usage_for_run(run_id)

    assert found[MemoryUsageStage.SELECTOR].selected_slugs == ("risk-preference", "project-rule")


async def test_usage_upsert_preserves_the_first_created_at(
    live_engine: AsyncEngine,
    owner: User,
    owned_thread: Thread,
) -> None:
    """HITL 续跑重写 selector 账时，不得把费用挪到重写当天。"""
    run_id = uuid4().hex
    await RunRepository(live_engine).create(run_id=run_id, thread_id=owned_thread.id, user_id=owner.id)
    repository = MemoryJobRepository(live_engine)
    first = MemoryUsage(
        run_id=run_id,
        thread_id=owned_thread.id,
        stage=MemoryUsageStage.SELECTOR,
        model="selector-model",
        tokens=TokenUsage(input_uncached=2),
        cost_yuan=0.01,
        duration_ms=3,
    )
    await repository.record_usage(first)
    original = datetime(2026, 1, 2, 3, 4, tzinfo=UTC)
    async with live_engine.begin() as connection:
        await connection.execute(
            text("UPDATE memory_usage SET created_at = :created_at WHERE run_id = :run_id"),
            {"created_at": original, "run_id": run_id},
        )

    await repository.record_usage(
        MemoryUsage(
            run_id=run_id,
            thread_id=owned_thread.id,
            stage=MemoryUsageStage.SELECTOR,
            model="selector-model",
            tokens=TokenUsage(input_uncached=5),
            cost_yuan=0.02,
            duration_ms=4,
        )
    )

    async with live_engine.connect() as connection:
        found = await connection.execute(
            text("SELECT created_at, cost_yuan FROM memory_usage WHERE run_id = :run_id"),
            {"run_id": run_id},
        )
        row = found.mappings().one()
    assert row["created_at"] == original
    assert row["cost_yuan"] == 0.02
