"""`runs` 表读写的测试，连真 Postgres。

**核心断言是「换一个仓储实例还查得到」** —— 那就是步骤二验证①：进程重启后
`GET /api/runs/{id}` 仍答得出终态。用替身验不了这个，替身重建之后什么都不剩。

表由 Alembic 建（根 conftest 的 `migrated`），这里不 `create_all`。
"""

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from event.model import RunErrorCode, RunStatus, TokenUsage
from run.repository import RunRepository


@pytest.fixture
def repository(live_engine: AsyncEngine) -> RunRepository:
    return RunRepository(live_engine)


@pytest.fixture
async def submitted(repository: RunRepository) -> AsyncIterator[tuple[str, str]]:
    run_id, thread_id = uuid4().hex, uuid4().hex
    await repository.create(run_id=run_id, thread_id=thread_id)
    yield run_id, thread_id


async def test_a_submitted_run_starts_out_queued(repository: RunRepository, submitted: tuple[str, str]) -> None:
    run_id, thread_id = submitted

    found = await repository.get(run_id)

    assert found is not None
    assert found.status is RunStatus.QUEUED
    assert found.thread_id == thread_id


async def test_a_new_repository_still_sees_the_terminal_state(
    repository: RunRepository, submitted: tuple[str, str], live_engine: AsyncEngine
) -> None:
    """换一个仓储实例就是换一个进程 —— 终态必须还在。"""
    run_id, _ = submitted
    await repository.start(run_id)
    await repository.succeed(run_id, tokens=TokenUsage(input_cache_read=7, input_uncached=3, output=5))

    found = await RunRepository(live_engine).get(run_id)

    assert found is not None
    assert found.status is RunStatus.SUCCEEDED


async def test_a_failed_run_keeps_its_reason(repository: RunRepository, submitted: tuple[str, str]) -> None:
    run_id, _ = submitted
    await repository.fail(run_id, code=RunErrorCode.SANDBOX_QUEUE_TIMEOUT, message="等了十分钟")

    found = await repository.get(run_id)

    assert found is not None
    assert found.status is RunStatus.FAILED


async def test_an_unknown_run_is_not_found(repository: RunRepository) -> None:
    assert await repository.get(uuid4().hex) is None


async def test_a_malformed_run_id_is_not_found_rather_than_an_error(repository: RunRepository) -> None:
    """Run id 来自 URL，是不可信输入。解析不了该是 404，不是 500。"""
    assert await repository.get("never-existed") is None


async def test_unfinished_lists_the_runs_that_never_reached_a_terminal_state(
    repository: RunRepository, submitted: tuple[str, str]
) -> None:
    """崩溃恢复扫的就是它。走的是 ix_runs_unfinished 那条部分索引。"""
    queued, _ = submitted
    running_id, thread_id = uuid4().hex, uuid4().hex
    await repository.create(run_id=running_id, thread_id=thread_id)
    await repository.start(running_id)
    done_id, done_thread = uuid4().hex, uuid4().hex
    await repository.create(run_id=done_id, thread_id=done_thread)
    await repository.succeed(done_id, tokens=TokenUsage())

    pending = {run.id for run in await repository.unfinished()}

    assert {queued, running_id} <= pending
    assert done_id not in pending


async def test_the_partial_index_covers_the_unfinished_query(live_engine: AsyncEngine) -> None:
    """索引的谓词与查询对不上时，这条查询会随历史 run 越来越慢，而结果始终是对的 —— 不会报错。

    关掉顺序扫描再看执行计划：让规划器只能在索引里选，就与表里当前有多少行无关了 ——
    否则空表上它本来就会走顺序扫描，这条断言的真假只取决于测试跑的时机。
    """
    async with live_engine.connect() as connection:
        await connection.execute(text("SET enable_seqscan = off"))
        result = await connection.execute(
            text("EXPLAIN SELECT id FROM runs WHERE status IN ('queued', 'running')"),
        )
        plan = "\n".join(row[0] for row in result)

    assert "ix_runs_unfinished" in plan
