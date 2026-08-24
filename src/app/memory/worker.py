"""独立消费成功 run 产生的 memory outbox。"""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import Protocol

from app.event.model import TokenUsage
from app.memory.consolidator import CONSOLIDATION_INPUT_LIMIT, CONSOLIDATION_THRESHOLD, MemoryConsolidator
from app.memory.extractor import ExtractionResult, MemoryExtractor
from app.memory.job import MemoryJob, MemoryUsage, MemoryUsageStage
from app.memory.store import MemoryCapacityError, MemoryRecord, MemoryStoreSnapshot, MemoryVersionConflictError

logger = logging.getLogger(__name__)

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_POLL_SECOND = 1.0
DEFAULT_STALE_SECOND = 30 * 60.0
DISCARDED_THREAD_REASON = "thread_deleted"
CONSOLIDATION_SKIPPED_REASON = "below_threshold"
MEMORY_CAPACITY_REASON = "memory_capacity"


class MemoryJobRepositoryProtocol(Protocol):
    """consumer 对 outbox 与额外用量账的最小要求。"""

    async def claim(self) -> MemoryJob | None:
        """互斥领取一条任务。"""
        ...

    async def complete(self, job_id: str, *, accepted_count: int, rejection_reasons: list[str]) -> bool:
        """写下成功终态与准入审计。"""
        ...

    async def discard(self, job_id: str, *, reason: str) -> bool:
        """丢弃已删 thread 的迟到任务。"""
        ...

    async def requeue(self, job_id: str, *, error: str) -> bool:
        """把可重试失败放回队列。"""
        ...

    async def fail(self, job_id: str, *, error: str) -> bool:
        """写下超过重试上限的终态失败。"""
        ...

    async def record_usage(self, usage: MemoryUsage) -> None:
        """写一条分阶段用量。"""
        ...

    async def usage_for_run(self, run_id: str) -> dict[MemoryUsageStage, MemoryUsage]:
        """读已有用量，便于把重试产生的费用累加而非覆盖。"""
        ...


class MemoryStorageProtocol(Protocol):
    """consumer 使用的 thread 隔离记忆存储边界。"""

    async def export(self, thread_id: str) -> MemoryStoreSnapshot:
        """同一次读取全量正文与版本，不得创建已删 thread 目录。"""
        ...

    async def write(self, thread_id: str, record: MemoryRecord) -> object:
        """写入一条经准入的记忆。"""
        ...

    async def replace(
        self,
        thread_id: str,
        records: tuple[MemoryRecord, ...],
        *,
        expected_version: str | None = None,
    ) -> object:
        """按版本全量替换；冲突不得覆盖并发新值。"""
        ...


class ThreadGuardProtocol(Protocol):
    """读 memdir 之前的 thread 软删除与归属守卫。"""

    async def active(self, thread_id: str, *, user_id: str) -> bool:
        """Thread 是否仍属于该用户且未软删除。"""
        ...


class MemoryCostProtocol(Protocol):
    """把辅助模型 token 换算为评估使用的人民币成本。"""

    def yuan(self, model: str, tokens: TokenUsage) -> float:
        """返回这一次模型用量的成本。"""
        ...


class MemoryJobRunnerProtocol(Protocol):
    """常驻循环驱动的单次消费边界。"""

    async def run_once(self) -> bool:
        """处理到任务返回 True，暂无任务返回 False。"""
        ...


class MemoryStaleRepositoryProtocol(Protocol):
    """常驻循环启动时恢复崩溃遗留任务的最小边界。"""

    async def requeue_stale(self, *, before: datetime) -> int:
        """把指定时刻之前仍为 running 的任务放回队列。"""
        ...


class MemoryRollbackError(RuntimeError):
    """整理替换失败，且原 snapshot 也未能恢复。"""


class MemoryJobWorker:
    """领取并处理一条记忆抽取 outbox。

    Args:
        repository: outbox 终态与额外模型用量仓储。
        thread_guard: 已删 thread 的最后一道无创建守卫。
        storage: 受控 memory service 适配器。
        extractor: 严格候选抽取与准入。
        consolidator: 最多二十条的全或无整理。
        model_name: extractor/consolidator 共用辅助模型名。
        cost: 当前辅助模型的成本换算器。
        max_attempts: 含本次在内的最大处理次数。
    """

    def __init__(
        self,
        *,
        repository: MemoryJobRepositoryProtocol,
        thread_guard: ThreadGuardProtocol,
        storage: MemoryStorageProtocol,
        extractor: MemoryExtractor,
        consolidator: MemoryConsolidator,
        model_name: str,
        cost: MemoryCostProtocol,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> None:
        if not model_name:
            raise ValueError("记忆辅助模型名不能为空")
        if max_attempts <= 0:
            raise ValueError("记忆 job 重试上限必须大于 0")
        self._repository = repository
        self._thread_guard = thread_guard
        self._storage = storage
        self._extractor = extractor
        self._consolidator = consolidator
        self._model_name = model_name
        self._cost = cost
        self._max_attempts = max_attempts

    async def run_once(self) -> bool:
        """消费一条任务；队列暂无任务时返回 False。"""
        job = await self._repository.claim()
        if job is None:
            return False

        stage = "guard"
        accepted_count = 0
        rejection_reasons: list[str] = []
        try:
            if not await self._thread_guard.active(job.thread_id, user_id=job.user_id):
                await self._ensure_zero_usage(job, reason=DISCARDED_THREAD_REASON)
                await self._repository.discard(job.id, reason=DISCARDED_THREAD_REASON)
                return True

            stage = "read"
            existing_snapshot = await self._storage.export(job.thread_id)
            stage = "extractor"
            extracted = await self._extract(job, existing_snapshot.records)
            rejection_reasons = [item.reason.value for item in extracted.rejected]

            stage = "write"
            for record in extracted.records:
                await self._storage.write(job.thread_id, record)
                accepted_count += 1
            stage = "read"
            current_snapshot = await self._storage.export(job.thread_id)
            current = current_snapshot.records

            stage = "consolidator"
            if len(current) >= CONSOLIDATION_THRESHOLD:
                consolidated = await self._consolidate(job, current)
                if consolidated != current:
                    stage = "replace"
                    await self._replace_with_rollback(job.thread_id, consolidated, snapshot=current_snapshot)
            else:
                await self._record_usage(
                    job,
                    stage=MemoryUsageStage.CONSOLIDATOR,
                    tokens=TokenUsage(),
                    started_ns=None,
                    hit_count=0,
                    rejected_count=0,
                    fallback_reason=CONSOLIDATION_SKIPPED_REASON,
                )

            stage = "complete"
            await self._repository.complete(
                job.id,
                accepted_count=accepted_count,
                rejection_reasons=rejection_reasons,
            )
        except MemoryCapacityError:
            logger.info("memory job 达到容量上限：job_id=%s stage=%s", job.id, stage)
            await self._complete_capacity(
                job,
                accepted_count=accepted_count,
                rejection_reasons=rejection_reasons,
            )
        except Exception as exc:
            # 正文或模型原始错误可能含凭据，不写进 PG/日志；只留阶段和异常类型。
            error = f"{stage}失败：{type(exc).__name__}"
            logger.warning(
                "memory job 处理失败：job_id=%s stage=%s error_type=%s",
                job.id,
                stage,
                type(exc).__name__,
            )
            if stage in {"guard", "read", "extractor", "write"}:
                try:
                    await self._ensure_zero_usage(job, reason=f"{stage}_failed")
                except Exception as usage_error:
                    logger.warning(
                        "memory job 跳过阶段记账失败：job_id=%s error_type=%s",
                        job.id,
                        type(usage_error).__name__,
                    )
            if job.attempts < self._max_attempts:
                await self._repository.requeue(job.id, error=error)
            else:
                await self._repository.fail(job.id, error=error)
        return True

    async def _complete_capacity(
        self,
        job: MemoryJob,
        *,
        accepted_count: int,
        rejection_reasons: list[str],
    ) -> None:
        """容量不足是可审计跳过，不重试同一批模型调用。"""
        try:
            await self._ensure_zero_usage(job, reason=MEMORY_CAPACITY_REASON)
        except Exception as usage_error:
            logger.warning(
                "memory job 容量跳过记账失败：job_id=%s error_type=%s",
                job.id,
                type(usage_error).__name__,
            )
        await self._repository.complete(
            job.id,
            accepted_count=accepted_count,
            rejection_reasons=[*rejection_reasons, MEMORY_CAPACITY_REASON],
        )

    async def _extract(self, job: MemoryJob, existing: tuple[MemoryRecord, ...]) -> ExtractionResult:
        """执行抽取，无论 schema/模型是否成功都记已发生的用量。"""
        tokens = TokenUsage()

        def collect(usage: TokenUsage) -> None:
            nonlocal tokens
            tokens = tokens + usage

        started = time.perf_counter_ns()
        try:
            result = await self._extractor.extract(job.messages, existing=existing, usage=collect)
        except Exception as exc:
            await self._record_usage(
                job,
                stage=MemoryUsageStage.EXTRACTOR,
                tokens=tokens,
                started_ns=started,
                hit_count=0,
                rejected_count=1,
                fallback_reason=type(exc).__name__,
            )
            raise
        await self._record_usage(
            job,
            stage=MemoryUsageStage.EXTRACTOR,
            tokens=tokens,
            started_ns=started,
            hit_count=len(result.records),
            rejected_count=len(result.rejected),
        )
        return result

    async def _consolidate(
        self,
        job: MemoryJob,
        records: tuple[MemoryRecord, ...],
    ) -> tuple[MemoryRecord, ...]:
        """执行整理，严格校验失败也记下这次模型调用。"""
        tokens = TokenUsage()

        def collect(usage: TokenUsage) -> None:
            nonlocal tokens
            tokens = tokens + usage

        started = time.perf_counter_ns()
        try:
            result = await self._consolidator.consolidate(records, usage=collect)
        except Exception as exc:
            await self._record_usage(
                job,
                stage=MemoryUsageStage.CONSOLIDATOR,
                tokens=tokens,
                started_ns=started,
                hit_count=0,
                rejected_count=1,
                fallback_reason=type(exc).__name__,
            )
            raise
        untouched_count = max(0, len(records) - CONSOLIDATION_INPUT_LIMIT)
        await self._record_usage(
            job,
            stage=MemoryUsageStage.CONSOLIDATOR,
            tokens=tokens,
            started_ns=started,
            hit_count=max(0, len(result) - untouched_count),
            rejected_count=0,
        )
        return result

    async def _record_usage(
        self,
        job: MemoryJob,
        *,
        stage: MemoryUsageStage,
        tokens: TokenUsage,
        started_ns: int | None,
        hit_count: int,
        rejected_count: int,
        fallback_reason: str | None = None,
    ) -> None:
        """按 run/stage 累加重试调用，避免 upsert 只留最后一笔费用。"""
        duration_ms = 0 if started_ns is None else max(0, (time.perf_counter_ns() - started_ns) // 1_000_000)
        cost_yuan = self._cost.yuan(self._model_name, tokens)
        previous = (await self._repository.usage_for_run(job.run_id)).get(stage)
        if previous is not None:
            tokens = previous.tokens + tokens
            cost_yuan += previous.cost_yuan
            duration_ms += previous.duration_ms
            hit_count += previous.hit_count
            rejected_count += previous.rejected_count
            fallback_reason = fallback_reason or previous.fallback_reason
        await self._repository.record_usage(
            MemoryUsage(
                run_id=job.run_id,
                thread_id=job.thread_id,
                job_id=job.id,
                stage=stage,
                model=self._model_name,
                tokens=tokens,
                cost_yuan=cost_yuan,
                duration_ms=duration_ms,
                hit_count=hit_count,
                rejected_count=rejected_count,
                fallback_reason=fallback_reason,
            )
        )

    async def _ensure_zero_usage(self, job: MemoryJob, *, reason: str) -> None:
        """为未调用的抽取/整理阶段落显式零账，避免把跳过误报成账本缺失。"""
        existing = await self._repository.usage_for_run(job.run_id)
        for stage in (MemoryUsageStage.EXTRACTOR, MemoryUsageStage.CONSOLIDATOR):
            if stage in existing:
                continue
            await self._record_usage(
                job,
                stage=stage,
                tokens=TokenUsage(),
                started_ns=None,
                hit_count=0,
                rejected_count=0,
                fallback_reason=reason,
            )

    async def _replace_with_rollback(
        self,
        thread_id: str,
        replacement: tuple[MemoryRecord, ...],
        *,
        snapshot: MemoryStoreSnapshot,
    ) -> None:
        """全量替换失败时立即用替换前 snapshot 恢复。"""
        try:
            await self._storage.replace(thread_id, replacement, expected_version=snapshot.version)
        except MemoryVersionConflictError:
            # 409 表示另一个调用者已提交新值；旧 snapshot 绝不能覆盖它。
            raise
        except Exception:
            try:
                await self._storage.replace(
                    thread_id,
                    snapshot.records,
                    expected_version=snapshot.version,
                )
            except Exception as rollback_error:
                raise MemoryRollbackError("记忆整理替换与 snapshot 恢复均失败") from rollback_error
            raise


class MemoryWorkerLoop:
    """以可唤醒轮询持续驱动独立 memory job worker。"""

    def __init__(
        self,
        *,
        runner: MemoryJobRunnerProtocol,
        poll_second: float = DEFAULT_POLL_SECOND,
        stale_repository: MemoryStaleRepositoryProtocol | None = None,
        stale_second: float = DEFAULT_STALE_SECOND,
    ) -> None:
        if poll_second <= 0:
            raise ValueError("记忆 worker 轮询间隔必须大于 0")
        if stale_second <= 0:
            raise ValueError("记忆 job 失联阈值必须大于 0")
        self._runner = runner
        self._poll_second = poll_second
        self._stale_repository = stale_repository
        self._stale_second = stale_second
        self._next_stale_sweep: float | None = None
        self._stopped = asyncio.Event()

    async def run(self) -> None:
        """持续消费；stop 后等待正在执行的 job 结束再返回。"""
        await self._recover_stale(startup=True)
        while not self._stopped.is_set():
            await self._recover_stale_if_due()
            try:
                consumed = await self._runner.run_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("memory worker 单次消费异常：error_type=%s", type(exc).__name__)
                consumed = False

            if self._stopped.is_set():
                return
            if not consumed:
                await self._wait_for_work()

    def stop(self) -> None:
        """请求停止并立即唤醒空队列等待，不取消当前 job。"""
        self._stopped.set()

    async def _wait_for_work(self) -> None:
        timeout = self._poll_second
        if self._next_stale_sweep is not None:
            timeout = min(timeout, max(0.0, self._next_stale_sweep - time.monotonic()))
        with suppress(TimeoutError):
            await asyncio.wait_for(self._stopped.wait(), timeout=timeout)

    async def _recover_stale_if_due(self) -> None:
        if self._next_stale_sweep is None or time.monotonic() < self._next_stale_sweep:
            return
        await self._recover_stale(startup=False)

    async def _recover_stale(self, *, startup: bool) -> None:
        if self._stale_repository is None:
            return
        now = datetime.now(UTC)
        before = now if startup else now - timedelta(seconds=self._stale_second)
        count = await self._stale_repository.requeue_stale(before=before)
        self._next_stale_sweep = time.monotonic() + self._stale_second
        if count:
            logger.warning("memory worker 已恢复崩溃遗留任务：count=%d", count)
