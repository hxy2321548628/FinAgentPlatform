"""记忆抽取 outbox、消费仓储与额外模型用量账。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Column, Enum, Index, UniqueConstraint, text, update
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import Field as SqlField
from sqlmodel import SQLModel, col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.event.model import TokenUsage

MEMORY_JOB_TABLE = "memory_jobs"
MEMORY_USAGE_TABLE = "memory_usage"


def _value_column(enum: type[StrEnum]) -> Column[Enum]:
    """把字符串枚举按 value 而非成员名存储。"""
    return Column(
        Enum(enum, values_callable=lambda values: [one.value for one in values], native_enum=False),
        nullable=False,
    )


class MemoryJobStatus(StrEnum):
    """记忆抽取任务的状态。"""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DISCARDED = "discarded"


class MemoryUsageStage(StrEnum):
    """额外模型调用所属的记忆环节。"""

    SELECTOR = "selector"
    EXTRACTOR = "extractor"
    CONSOLIDATOR = "consolidator"


class MemoryJobPayload(BaseModel):
    """成功终态与 outbox 同事务写入的受控快照。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    thread_id: str = Field(min_length=1, description="记忆所属 thread")
    user_id: str = Field(min_length=1, description="仅用于任务归属与删除守卫")
    messages: list[dict[str, str]] = Field(min_length=1, description="Agent 给出的受控问答快照")


class MemoryJobRecord(SQLModel, table=True):
    """一条待抽取或已处理的记忆 outbox。"""

    __tablename__ = MEMORY_JOB_TABLE
    __table_args__ = (
        UniqueConstraint("run_id", name="uq_memory_jobs_run"),
        Index(
            "ix_memory_jobs_queued",
            "status",
            "created_at",
            postgresql_where=text("status = 'queued'"),
        ),
    )

    id: UUID = SqlField(primary_key=True)
    run_id: UUID = SqlField(foreign_key="runs.id")
    thread_id: UUID = SqlField(foreign_key="threads.id")
    user_id: UUID = SqlField(foreign_key="users.id")
    status: MemoryJobStatus = SqlField(sa_column=_value_column(MemoryJobStatus))
    snapshot: list[dict[str, str]] = SqlField(sa_column=Column(JSONB, nullable=False))
    attempts: int = SqlField(default=0)
    accepted_count: int = SqlField(default=0)
    rejected_count: int = SqlField(default=0)
    rejection_reasons: list[str] = SqlField(default_factory=list, sa_column=Column(JSONB, nullable=False))
    last_error: str | None = SqlField(default=None)
    created_at: datetime
    started_at: datetime | None = SqlField(default=None)
    ended_at: datetime | None = SqlField(default=None)


class MemoryUsageRecord(SQLModel, table=True):
    """选择、抽取或整理的一次模型用量审计。"""

    __tablename__ = MEMORY_USAGE_TABLE
    __table_args__ = (
        UniqueConstraint("run_id", "stage", name="uq_memory_usage_run_stage"),
        Index("ix_memory_usage_thread_created", "thread_id", "created_at"),
    )

    id: UUID = SqlField(primary_key=True)
    run_id: UUID = SqlField(foreign_key="runs.id")
    thread_id: UUID = SqlField(foreign_key="threads.id")
    job_id: UUID | None = SqlField(default=None, foreign_key=f"{MEMORY_JOB_TABLE}.id")
    stage: MemoryUsageStage = SqlField(sa_column=_value_column(MemoryUsageStage))
    model: str
    tokens_cache_read: int = SqlField(default=0)
    tokens_uncached: int = SqlField(default=0)
    tokens_output: int = SqlField(default=0)
    cost_yuan: float = SqlField(default=0.0)
    duration_ms: int = SqlField(default=0)
    hit_count: int = SqlField(default=0)
    rejected_count: int = SqlField(default=0)
    fallback_reason: str | None = SqlField(default=None)
    included_in_run: bool = SqlField(default=False)
    selected_slugs: list[str] = SqlField(default_factory=list, sa_column=Column(JSONB, nullable=False))
    created_at: datetime


@dataclass(frozen=True)
class MemoryJob:
    """消费者领到的一条抽取任务。"""

    id: str
    run_id: str
    thread_id: str
    user_id: str
    messages: list[dict[str, str]]
    attempts: int


@dataclass(frozen=True)
class MemoryUsage:
    """一次记忆模型调用的持久化审计。"""

    run_id: str
    thread_id: str
    stage: MemoryUsageStage
    model: str
    tokens: TokenUsage
    cost_yuan: float
    duration_ms: int
    hit_count: int = 0
    rejected_count: int = 0
    fallback_reason: str | None = None
    included_in_run: bool = False
    selected_slugs: tuple[str, ...] = ()
    job_id: str | None = None


class MemoryJobRepository:
    """消费成功终态 outbox，并单独保存三个记忆环节的用量。"""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def claim(self) -> MemoryJob | None:
        """互斥领走最早的一条任务；多 worker 不会领到同一行。"""
        now = datetime.now(UTC)
        async with AsyncSession(self._engine) as session:
            found = await session.exec(
                select(MemoryJobRecord)
                .where(col(MemoryJobRecord.status) == MemoryJobStatus.QUEUED)
                .order_by(col(MemoryJobRecord.created_at), col(MemoryJobRecord.id))
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            record = found.first()
            if record is None:
                return None
            record.status = MemoryJobStatus.RUNNING
            record.attempts += 1
            record.started_at = now
            record.last_error = None
            session.add(record)
            # commit 默认会过期 ORM 字段；先物化，避免随后隐式异步刷新触发 MissingGreenlet。
            job = _to_job(record)
            await session.commit()
            return job

    async def requeue_stale(self, *, before: datetime) -> int:
        """把 worker 崩溃时遗留的 running 任务放回队列。"""
        statement = (
            update(MemoryJobRecord)
            .where(
                col(MemoryJobRecord.status) == MemoryJobStatus.RUNNING,
                col(MemoryJobRecord.started_at) < before,
            )
            .values(status=MemoryJobStatus.QUEUED, started_at=None, last_error="消费者超时，等待重试")
        )
        async with AsyncSession(self._engine) as session:
            result = await session.exec(statement)
            await session.commit()
        return int(result.rowcount)

    async def complete(
        self,
        job_id: str,
        *,
        accepted_count: int,
        rejection_reasons: list[str],
    ) -> bool:
        """记录抽取结果；重复完成是幂等空操作。"""
        return await self._finish(
            job_id,
            status=MemoryJobStatus.SUCCEEDED,
            accepted_count=accepted_count,
            rejected_count=len(rejection_reasons),
            rejection_reasons=rejection_reasons,
            last_error=None,
        )

    async def discard(self, job_id: str, *, reason: str) -> bool:
        """丢弃已删除 thread 等不应再执行的任务。"""
        return await self._finish(
            job_id,
            status=MemoryJobStatus.DISCARDED,
            accepted_count=0,
            rejected_count=0,
            rejection_reasons=[reason],
            last_error=None,
        )

    async def requeue(self, job_id: str, *, error: str) -> bool:
        """把本次可重试失败放回队列，仅处理仍在 running 的行。"""
        identifier = _parse(job_id)
        if identifier is None:
            return False
        statement = (
            update(MemoryJobRecord)
            .where(
                col(MemoryJobRecord.id) == identifier,
                col(MemoryJobRecord.status) == MemoryJobStatus.RUNNING,
            )
            .values(
                status=MemoryJobStatus.QUEUED,
                started_at=None,
                ended_at=None,
                last_error=error,
            )
        )
        async with AsyncSession(self._engine) as session:
            result = await session.exec(statement)
            await session.commit()
        return bool(result.rowcount)

    async def fail(self, job_id: str, *, error: str) -> bool:
        """记下终态失败；主 run 已成功，不受这次失败影响。"""
        return await self._finish(
            job_id,
            status=MemoryJobStatus.FAILED,
            accepted_count=0,
            rejected_count=0,
            rejection_reasons=[],
            last_error=error,
        )

    async def record_usage(self, usage: MemoryUsage) -> None:
        """按 run/stage 幂等写账，崩溃重投不会把同一笔费用累加两次。"""
        now = datetime.now(UTC)
        values = {
            "id": uuid4(),
            "run_id": UUID(usage.run_id),
            "thread_id": UUID(usage.thread_id),
            "job_id": UUID(usage.job_id) if usage.job_id is not None else None,
            "stage": usage.stage,
            "model": usage.model,
            "tokens_cache_read": usage.tokens.input_cache_read,
            "tokens_uncached": usage.tokens.input_uncached,
            "tokens_output": usage.tokens.output,
            "cost_yuan": usage.cost_yuan,
            "duration_ms": usage.duration_ms,
            "hit_count": usage.hit_count,
            "rejected_count": usage.rejected_count,
            "fallback_reason": usage.fallback_reason,
            "included_in_run": usage.included_in_run,
            "selected_slugs": list(usage.selected_slugs),
            "created_at": now,
        }
        statement = insert(MemoryUsageRecord).values(**values)
        statement = statement.on_conflict_do_update(
            constraint="uq_memory_usage_run_stage",
            set_={key: value for key, value in values.items() if key not in {"id", "run_id", "stage", "created_at"}},
        )
        async with AsyncSession(self._engine) as session:
            await session.exec(statement)
            await session.commit()

    async def usage_for_run(self, run_id: str) -> dict[MemoryUsageStage, MemoryUsage]:
        """读取一条 run 的记忆分项账；缺席保留为缺席，不伪装成零。"""
        identifier = _parse(run_id)
        if identifier is None:
            return {}
        async with AsyncSession(self._engine) as session:
            found = await session.exec(select(MemoryUsageRecord).where(col(MemoryUsageRecord.run_id) == identifier))
        return {record.stage: _to_usage(record) for record in found.all()}

    async def status_for_run(self, run_id: str) -> MemoryJobStatus | None:
        """读取一条 run 的记忆任务状态；没有 outbox 时保留为缺席。"""
        identifier = _parse(run_id)
        if identifier is None:
            return None
        async with AsyncSession(self._engine) as session:
            found = await session.exec(select(MemoryJobRecord).where(col(MemoryJobRecord.run_id) == identifier))
        record = found.first()
        return None if record is None else record.status

    async def _finish(
        self,
        job_id: str,
        *,
        status: MemoryJobStatus,
        accepted_count: int,
        rejected_count: int,
        rejection_reasons: list[str],
        last_error: str | None,
    ) -> bool:
        identifier = _parse(job_id)
        if identifier is None:
            return False
        statement = (
            update(MemoryJobRecord)
            .where(
                col(MemoryJobRecord.id) == identifier,
                col(MemoryJobRecord.status) == MemoryJobStatus.RUNNING,
            )
            .values(
                status=status,
                accepted_count=accepted_count,
                rejected_count=rejected_count,
                rejection_reasons=rejection_reasons,
                last_error=last_error,
                ended_at=datetime.now(UTC),
            )
        )
        async with AsyncSession(self._engine) as session:
            result = await session.exec(statement)
            await session.commit()
        return bool(result.rowcount)


def _to_job(record: MemoryJobRecord) -> MemoryJob:
    return MemoryJob(
        id=record.id.hex,
        run_id=record.run_id.hex,
        thread_id=record.thread_id.hex,
        user_id=record.user_id.hex,
        messages=record.snapshot,
        attempts=record.attempts,
    )


def _to_usage(record: MemoryUsageRecord) -> MemoryUsage:
    return MemoryUsage(
        run_id=record.run_id.hex,
        thread_id=record.thread_id.hex,
        job_id=None if record.job_id is None else record.job_id.hex,
        stage=record.stage,
        model=record.model,
        tokens=TokenUsage(
            input_cache_read=record.tokens_cache_read,
            input_uncached=record.tokens_uncached,
            output=record.tokens_output,
        ),
        cost_yuan=record.cost_yuan,
        duration_ms=record.duration_ms,
        hit_count=record.hit_count,
        rejected_count=record.rejected_count,
        fallback_reason=record.fallback_reason,
        included_in_run=record.included_in_run,
        selected_slugs=tuple(record.selected_slugs),
    )


def _parse(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None
