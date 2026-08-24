"""独立 memory job consumer 的终态、回滚、重试与计量测试。"""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import cast

from langchain_core.messages import AIMessage

from app.event.model import TokenUsage
from app.memory.consolidator import MemoryConsolidator
from app.memory.extractor import MemoryExtractor
from app.memory.job import MemoryJob, MemoryUsage, MemoryUsageStage
from app.memory.model import SelectorModelProtocol
from app.memory.store import MemoryCapacityError, MemoryRecord, MemoryStoreSnapshot, MemoryVersionConflictError
from app.memory.worker import (
    MemoryCostProtocol,
    MemoryJobRepositoryProtocol,
    MemoryJobWorker,
    MemoryStorageProtocol,
    MemoryWorkerLoop,
    ThreadGuardProtocol,
)


class FakeModel:
    def __init__(self, response: str, *, error: Exception | None = None, input_tokens: int = 20) -> None:
        self.response = response
        self.error = error
        self.input_tokens = input_tokens
        self.calls = 0

    async def ainvoke(self, prompt: str) -> AIMessage:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return AIMessage(
            content=self.response,
            usage_metadata={
                "input_tokens": self.input_tokens,
                "output_tokens": 4,
                "total_tokens": self.input_tokens + 4,
                "input_token_details": {"cache_read": 8},
            },
        )


class FakeRepository:
    def __init__(self, job: MemoryJob | None) -> None:
        self.job = job
        self.claimed = 0
        self.completed: list[tuple[str, int, list[str]]] = []
        self.discarded: list[tuple[str, str]] = []
        self.requeued: list[tuple[str, str]] = []
        self.failed: list[tuple[str, str]] = []
        self.usage: dict[MemoryUsageStage, MemoryUsage] = {}

    async def claim(self) -> MemoryJob | None:
        self.claimed += 1
        found, self.job = self.job, None
        return found

    async def complete(self, job_id: str, *, accepted_count: int, rejection_reasons: list[str]) -> bool:
        self.completed.append((job_id, accepted_count, rejection_reasons))
        return True

    async def discard(self, job_id: str, *, reason: str) -> bool:
        self.discarded.append((job_id, reason))
        return True

    async def requeue(self, job_id: str, *, error: str) -> bool:
        self.requeued.append((job_id, error))
        return True

    async def fail(self, job_id: str, *, error: str) -> bool:
        self.failed.append((job_id, error))
        return True

    async def record_usage(self, usage: MemoryUsage) -> None:
        self.usage[usage.stage] = usage

    async def usage_for_run(self, run_id: str) -> dict[MemoryUsageStage, MemoryUsage]:
        return dict(self.usage)


class FakeThreadGuard:
    def __init__(self, active: bool = True) -> None:
        self.is_active = active
        self.calls: list[tuple[str, str]] = []

    async def active(self, thread_id: str, *, user_id: str) -> bool:
        self.calls.append((thread_id, user_id))
        return self.is_active


class FakeStorage:
    def __init__(self, records: list[MemoryRecord] | None = None) -> None:
        self.records = list(records or [])
        self.listed: list[str] = []
        self.written: list[MemoryRecord] = []
        self.replacements: list[tuple[MemoryRecord, ...]] = []
        self.replace_versions: list[str | None] = []
        self.version = 0
        self.fail_first_replace = False
        self.fail_every_replace = False
        self.conflict_first_replace = False
        self.capacity_on_write: int | None = None
        self.write_calls = 0

    async def export(self, thread_id: str) -> MemoryStoreSnapshot:
        self.listed.append(thread_id)
        return MemoryStoreSnapshot(records=tuple(self.records), version=f"v{self.version}")

    async def write(self, thread_id: str, record: MemoryRecord) -> None:
        self.write_calls += 1
        if self.capacity_on_write == self.write_calls:
            raise MemoryCapacityError("正文不得进入数据库或日志")
        self.written.append(record)
        self.records = [one for one in self.records if one.slug != record.slug]
        self.records.append(record)
        self.version += 1

    async def replace(
        self,
        thread_id: str,
        records: tuple[MemoryRecord, ...],
        *,
        expected_version: str | None = None,
    ) -> None:
        self.replacements.append(records)
        self.replace_versions.append(expected_version)
        if self.conflict_first_replace and len(self.replacements) == 1:
            self.records.append(a_record(99))
            self.version += 1
            raise MemoryVersionConflictError("并发版本已变化")
        if expected_version is not None and expected_version != f"v{self.version}":
            raise MemoryVersionConflictError("并发版本已变化")
        if self.fail_every_replace:
            raise OSError("api_key=do-not-persist-this")
        if self.fail_first_replace and len(self.replacements) == 1:
            raise OSError("api_key=do-not-persist-this")
        self.records = list(records)
        self.version += 1


class FakeCost:
    def yuan(self, model: str, tokens: TokenUsage) -> float:
        return (tokens.input_uncached + tokens.output) / 1_000


def a_job(*, attempts: int = 1) -> MemoryJob:
    return MemoryJob(
        id="job-1",
        run_id="run-1",
        thread_id="thread-1",
        user_id="user-1",
        messages=[
            {"role": "user", "content": "请记住我偏好制表符缩进"},
            {"role": "assistant", "content": "明白"},
        ],
        attempts=attempts,
    )


def a_record(index: int) -> MemoryRecord:
    return MemoryRecord(
        slug=f"item-{index}",
        name=f"item-{index}",
        description=f"描述 {index}",
        type="project",
        content=f"正文 {index}",
    )


def extracted_response() -> str:
    return json.dumps(
        [
            {
                "scope": "persistent",
                "name": "tab-preference",
                "description": "编码缩进偏好",
                "type": "user",
                "content": "教师偏好制表符缩进。",
            },
            {
                "scope": "current_task",
                "name": "temporary",
                "description": "本轮限制",
                "type": "feedback",
                "content": "当前任务不创建文件。",
            },
        ],
        ensure_ascii=False,
    )


def consolidated_response() -> str:
    return json.dumps(
        [
            {
                "name": "merged-project-facts",
                "description": "合并后的项目事实",
                "type": "project",
                "content": "项目的稳定事实。",
            }
        ],
        ensure_ascii=False,
    )


def a_consumer(
    repository: FakeRepository,
    storage: FakeStorage,
    *,
    guard: FakeThreadGuard | None = None,
    extractor_model: FakeModel | None = None,
    consolidator_model: FakeModel | None = None,
    max_attempts: int = 3,
) -> tuple[MemoryJobWorker, FakeModel, FakeModel]:
    extraction = extractor_model or FakeModel(extracted_response())
    consolidation = consolidator_model or FakeModel(consolidated_response(), input_tokens=30)
    consumer = MemoryJobWorker(
        repository=cast(MemoryJobRepositoryProtocol, repository),
        thread_guard=cast(ThreadGuardProtocol, guard or FakeThreadGuard()),
        storage=cast(MemoryStorageProtocol, storage),
        extractor=MemoryExtractor(model=cast(SelectorModelProtocol, extraction)),
        consolidator=MemoryConsolidator(model=cast(SelectorModelProtocol, consolidation)),
        model_name="aux-model",
        cost=cast(MemoryCostProtocol, FakeCost()),
        max_attempts=max_attempts,
    )
    return consumer, extraction, consolidation


async def test_no_claimed_job_returns_false_without_touching_dependencies() -> None:
    repository = FakeRepository(None)
    storage = FakeStorage()
    consumer, extraction, consolidation = a_consumer(repository, storage)

    assert await consumer.run_once() is False
    assert storage.listed == []
    assert extraction.calls == 0
    assert consolidation.calls == 0


async def test_deleted_thread_is_discarded_before_memory_is_read() -> None:
    repository = FakeRepository(a_job())
    storage = FakeStorage()
    guard = FakeThreadGuard(active=False)
    consumer, extraction, _ = a_consumer(repository, storage, guard=guard)

    assert await consumer.run_once() is True
    assert repository.discarded == [("job-1", "thread_deleted")]
    assert storage.listed == []
    assert extraction.calls == 0
    assert repository.usage[MemoryUsageStage.EXTRACTOR].tokens == TokenUsage()
    assert repository.usage[MemoryUsageStage.CONSOLIDATOR].tokens == TokenUsage()


async def test_extraction_writes_only_accepted_records_then_completes() -> None:
    repository = FakeRepository(a_job())
    storage = FakeStorage()
    consumer, _, consolidation = a_consumer(repository, storage)

    assert await consumer.run_once() is True

    assert [record.name for record in storage.written] == ["tab-preference"]
    assert repository.completed == [("job-1", 1, ["current_task"])]
    assert consolidation.calls == 0
    usage = repository.usage[MemoryUsageStage.EXTRACTOR]
    assert usage.model == "aux-model"
    assert usage.tokens == TokenUsage(input_cache_read=8, input_uncached=12, output=4)
    assert usage.duration_ms >= 0
    assert usage.hit_count == 1
    assert usage.rejected_count == 1
    assert usage.cost_yuan == 0.016
    assert usage.job_id == "job-1"
    skipped = repository.usage[MemoryUsageStage.CONSOLIDATOR]
    assert skipped.tokens == TokenUsage()
    assert skipped.cost_yuan == 0.0
    assert skipped.duration_ms == 0
    assert skipped.hit_count == 0
    assert skipped.rejected_count == 0
    assert skipped.fallback_reason == "below_threshold"


async def test_ten_records_trigger_consolidation_and_full_replacement() -> None:
    repository = FakeRepository(a_job())
    storage = FakeStorage([a_record(index) for index in range(9)])
    extraction = FakeModel(
        json.dumps(
            [
                {
                    "scope": "persistent",
                    "name": "tenth-fact",
                    "description": "第十条事实",
                    "type": "project",
                    "content": "第十条稳定事实。",
                }
            ],
            ensure_ascii=False,
        )
    )
    consumer, _, consolidation = a_consumer(repository, storage, extractor_model=extraction)

    await consumer.run_once()

    assert consolidation.calls == 1
    assert storage.listed == ["thread-1", "thread-1"]
    assert len(storage.replacements) == 1
    assert storage.replace_versions == ["v1"]
    assert [record.slug for record in storage.records] == ["merged-project-facts"]
    assert repository.completed == [("job-1", 1, [])]
    usage = repository.usage[MemoryUsageStage.CONSOLIDATOR]
    assert usage.model == "aux-model"
    assert usage.tokens == TokenUsage(input_cache_read=8, input_uncached=22, output=4)
    assert usage.cost_yuan == 0.026
    assert usage.duration_ms >= 0
    assert usage.hit_count == 1
    assert usage.rejected_count == 0


async def test_failed_full_replacement_restores_the_post_extraction_snapshot_and_requeues() -> None:
    repository = FakeRepository(a_job(attempts=1))
    original = [a_record(index) for index in range(9)]
    storage = FakeStorage(original)
    storage.fail_first_replace = True
    extraction = FakeModel(
        json.dumps(
            [
                {
                    "scope": "persistent",
                    "name": "tenth-fact",
                    "description": "第十条事实",
                    "type": "project",
                    "content": "第十条稳定事实。",
                }
            ],
            ensure_ascii=False,
        )
    )
    consumer, _, _ = a_consumer(repository, storage, extractor_model=extraction)

    await consumer.run_once()

    assert len(storage.replacements) == 2
    assert storage.replace_versions == ["v1", "v1"]
    assert tuple(storage.records) == storage.replacements[1]
    assert len(storage.records) == 10
    assert repository.completed == []
    assert repository.requeued == [("job-1", "replace失败：OSError")]
    assert "do-not-persist-this" not in repository.requeued[0][1]
    assert MemoryUsageStage.CONSOLIDATOR in repository.usage


async def test_concurrent_replacement_conflict_is_requeued_without_overwriting_the_new_value() -> None:
    repository = FakeRepository(a_job(attempts=1))
    storage = FakeStorage([a_record(index) for index in range(9)])
    storage.conflict_first_replace = True
    extraction = FakeModel(
        json.dumps(
            [
                {
                    "scope": "persistent",
                    "name": "tenth-fact",
                    "description": "第十条事实",
                    "type": "project",
                    "content": "第十条稳定事实。",
                }
            ],
            ensure_ascii=False,
        )
    )
    consumer, _, _ = a_consumer(repository, storage, extractor_model=extraction)

    await consumer.run_once()

    assert len(storage.replacements) == 1
    assert storage.replace_versions == ["v1"]
    assert "item-99" in {record.slug for record in storage.records}
    assert repository.requeued == [("job-1", "replace失败：MemoryVersionConflictError")]


async def test_capacity_limit_completes_without_retry_and_reports_partial_writes() -> None:
    repository = FakeRepository(a_job())
    storage = FakeStorage()
    storage.capacity_on_write = 2
    extraction = FakeModel(
        json.dumps(
            [
                {
                    "scope": "persistent",
                    "name": "first-fact",
                    "description": "第一条稳定事实",
                    "type": "project",
                    "content": "第一条事实。",
                },
                {
                    "scope": "persistent",
                    "name": "second-fact",
                    "description": "第二条稳定事实",
                    "type": "project",
                    "content": "第二条事实。",
                },
            ],
            ensure_ascii=False,
        )
    )
    consumer, _, consolidation = a_consumer(repository, storage, extractor_model=extraction)

    assert await consumer.run_once() is True
    assert await consumer.run_once() is False

    assert [record.slug for record in storage.written] == ["first-fact"]
    assert repository.completed == [("job-1", 1, ["memory_capacity"])]
    assert repository.requeued == []
    assert repository.failed == []
    assert extraction.calls == 1
    assert consolidation.calls == 0
    skipped = repository.usage[MemoryUsageStage.CONSOLIDATOR]
    assert skipped.tokens == TokenUsage()
    assert skipped.fallback_reason == "memory_capacity"


async def test_a_transient_model_failure_is_requeued_without_persisting_the_exception_body() -> None:
    repository = FakeRepository(a_job(attempts=1))
    storage = FakeStorage()
    model = FakeModel("[]", error=RuntimeError("api_key=do-not-persist-this"))
    consumer, _, _ = a_consumer(repository, storage, extractor_model=model)

    await consumer.run_once()

    assert repository.requeued == [("job-1", "extractor失败：RuntimeError")]
    assert repository.failed == []
    usage = repository.usage[MemoryUsageStage.EXTRACTOR]
    assert usage.tokens == TokenUsage()
    assert usage.hit_count == 0
    assert usage.rejected_count == 1
    assert usage.fallback_reason == "RuntimeError"
    skipped = repository.usage[MemoryUsageStage.CONSOLIDATOR]
    assert skipped.tokens == TokenUsage()
    assert skipped.cost_yuan == 0.0
    assert skipped.fallback_reason == "extractor_failed"


async def test_last_attempt_turns_the_job_failed_instead_of_requeueing() -> None:
    repository = FakeRepository(a_job(attempts=3))
    storage = FakeStorage()
    model = FakeModel("[]", error=RuntimeError("模型仍然不可用"))
    consumer, _, _ = a_consumer(repository, storage, extractor_model=model, max_attempts=3)

    await consumer.run_once()

    assert repository.requeued == []
    assert repository.failed == [("job-1", "extractor失败：RuntimeError")]


async def test_retried_stage_usage_is_accumulated_instead_of_overwritten() -> None:
    repository = FakeRepository(a_job())
    repository.usage[MemoryUsageStage.EXTRACTOR] = MemoryUsage(
        run_id="run-1",
        thread_id="thread-1",
        job_id="job-1",
        stage=MemoryUsageStage.EXTRACTOR,
        model="aux-model",
        tokens=TokenUsage(input_uncached=10, output=2),
        cost_yuan=0.012,
        duration_ms=7,
        hit_count=1,
        rejected_count=2,
    )
    storage = FakeStorage()
    consumer, _, _ = a_consumer(repository, storage)

    await consumer.run_once()

    usage = repository.usage[MemoryUsageStage.EXTRACTOR]
    assert usage.tokens == TokenUsage(input_cache_read=8, input_uncached=22, output=6)
    assert usage.cost_yuan == 0.028
    assert usage.duration_ms >= 7
    assert usage.hit_count == 2
    assert usage.rejected_count == 3


class FakeJobRunner:
    def __init__(self, results: list[bool | Exception]) -> None:
        self.results = results
        self.calls = 0
        self.called = asyncio.Event()

    async def run_once(self) -> bool:
        index = self.calls
        self.calls += 1
        self.called.set()
        result = self.results[index] if index < len(self.results) else False
        if isinstance(result, Exception):
            raise result
        return result


class FakeStaleRepository:
    def __init__(self) -> None:
        self.before: list[datetime] = []
        self.called_at: list[datetime] = []

    async def requeue_stale(self, *, before: datetime) -> int:
        self.called_at.append(datetime.now(UTC))
        self.before.append(before)
        return 1


async def test_worker_loop_requeues_crashed_jobs_once_at_startup() -> None:
    runner = FakeJobRunner([False])
    stale = FakeStaleRepository()
    started = datetime.now(UTC)
    loop = MemoryWorkerLoop(
        runner=runner,
        poll_second=60,
        stale_repository=stale,
        stale_second=1_800,
    )
    task = asyncio.create_task(loop.run())
    await runner.called.wait()
    loop.stop()
    await asyncio.wait_for(task, timeout=0.1)

    assert len(stale.before) == 1
    assert timedelta(0) <= stale.before[0] - started <= timedelta(seconds=1)


async def test_worker_loop_periodically_recovers_jobs_older_than_the_stale_threshold() -> None:
    runner = FakeJobRunner([False])
    stale = FakeStaleRepository()
    loop = MemoryWorkerLoop(
        runner=runner,
        poll_second=60,
        stale_repository=stale,
        stale_second=0.005,
    )
    task = asyncio.create_task(loop.run())

    async def wait_for_second_scan() -> None:
        while len(stale.before) < 2:
            await asyncio.sleep(0.001)

    await asyncio.wait_for(wait_for_second_scan(), timeout=0.1)
    loop.stop()
    await asyncio.wait_for(task, timeout=0.1)

    assert stale.called_at[1] - stale.before[1] >= timedelta(seconds=0.004)


async def test_worker_loop_waits_when_empty_and_stop_wakes_it_immediately() -> None:
    runner = FakeJobRunner([False])
    loop = MemoryWorkerLoop(runner=runner, poll_second=60)
    task = asyncio.create_task(loop.run())
    await runner.called.wait()
    await asyncio.sleep(0)

    assert runner.calls == 1
    loop.stop()
    await asyncio.wait_for(task, timeout=0.1)
    assert runner.calls == 1


async def test_worker_loop_stop_waits_for_the_current_job_to_finish() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    class BlockingRunner:
        async def run_once(self) -> bool:
            started.set()
            await release.wait()
            return True

    loop = MemoryWorkerLoop(runner=BlockingRunner(), poll_second=60)
    task = asyncio.create_task(loop.run())
    await started.wait()

    loop.stop()
    await asyncio.sleep(0)
    assert not task.done()
    release.set()
    await asyncio.wait_for(task, timeout=0.1)


async def test_worker_loop_survives_an_unexpected_run_once_error() -> None:
    runner = FakeJobRunner([RuntimeError("api_key=do-not-log-this"), False])
    loop = MemoryWorkerLoop(runner=runner, poll_second=0.001)
    task = asyncio.create_task(loop.run())

    async def wait_for_retry() -> None:
        while runner.calls < 2:
            await asyncio.sleep(0.001)

    await asyncio.wait_for(wait_for_retry(), timeout=0.1)
    loop.stop()
    await asyncio.wait_for(task, timeout=0.1)

    assert runner.calls >= 2
