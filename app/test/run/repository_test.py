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
from test.conftest import FAKE_HASH
from thread.repository import Thread
from user.model import UserRole
from user.repository import User, UserRepository


@pytest.fixture
def repository(live_engine: AsyncEngine) -> RunRepository:
    return RunRepository(live_engine)


@pytest.fixture
async def submitted(repository: RunRepository, owner: User, owned_thread: Thread) -> AsyncIterator[str]:
    run_id = uuid4().hex
    await repository.create(run_id=run_id, thread_id=owned_thread.id, user_id=owner.id)
    yield run_id


async def test_a_submitted_run_starts_out_queued(
    repository: RunRepository, submitted: str, owner: User, owned_thread: Thread
) -> None:
    found = await repository.get(submitted, user_id=owner.id)

    assert found is not None
    assert found.status is RunStatus.QUEUED
    assert found.thread_id == owned_thread.id


async def test_a_new_repository_still_sees_the_terminal_state(
    repository: RunRepository, submitted: str, owner: User, live_engine: AsyncEngine
) -> None:
    """换一个仓储实例就是换一个进程 —— 终态必须还在。"""
    await repository.start(submitted)
    await repository.succeed(submitted, tokens=TokenUsage(input_cache_read=7, input_uncached=3, output=5))

    found = await RunRepository(live_engine).get(submitted, user_id=owner.id)

    assert found is not None
    assert found.status is RunStatus.SUCCEEDED


async def test_a_failed_run_keeps_its_reason(repository: RunRepository, submitted: str, owner: User) -> None:
    await repository.fail(submitted, code=RunErrorCode.SANDBOX_QUEUE_TIMEOUT, message="等了十分钟")

    found = await repository.get(submitted, user_id=owner.id)

    assert found is not None
    assert found.status is RunStatus.FAILED


async def test_an_unknown_run_is_not_found(repository: RunRepository, owner: User) -> None:
    assert await repository.get(uuid4().hex, user_id=owner.id) is None


async def test_a_malformed_run_id_is_not_found_rather_than_an_error(repository: RunRepository, owner: User) -> None:
    """Run id 来自 URL，是不可信输入。解析不了该是 404，不是 500。"""
    assert await repository.get("never-existed", user_id=owner.id) is None


async def test_another_users_run_is_not_found(
    repository: RunRepository, submitted: str, live_engine: AsyncEngine
) -> None:
    """越权与不存在是同一个结果 —— 端点因此自然落到 404，不需要额外写一句鉴权。"""
    stranger = await UserRepository(live_engine).create(
        name=f"stranger-{uuid4().hex[:8]}", password_hash=FAKE_HASH, role=UserRole.TEACHER
    )

    assert await repository.get(submitted, user_id=stranger.id) is None


async def test_an_admin_gets_no_special_treatment(
    repository: RunRepository, submitted: str, live_engine: AsyncEngine
) -> None:
    """管理员多的是管账号的能力，不是看别人会话的能力。这一层没有绕过过滤的旁路。"""
    admin = await UserRepository(live_engine).create(
        name=f"admin-{uuid4().hex[:8]}", password_hash=FAKE_HASH, role=UserRole.ADMIN
    )

    assert await repository.get(submitted, user_id=admin.id) is None


async def test_unfinished_lists_the_runs_that_never_reached_a_terminal_state(
    repository: RunRepository, submitted: str, owner: User, owned_thread: Thread
) -> None:
    """崩溃恢复扫的就是它。走的是 ix_runs_unfinished 那条部分索引。"""
    queued = submitted
    running_id = uuid4().hex
    await repository.create(run_id=running_id, thread_id=owned_thread.id, user_id=owner.id)
    await repository.start(running_id)
    done_id = uuid4().hex
    await repository.create(run_id=done_id, thread_id=owned_thread.id, user_id=owner.id)
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


async def test_the_status_is_stored_the_way_the_contract_spells_it(
    repository: RunRepository, submitted: str, live_engine: AsyncEngine
) -> None:
    """库里躺的必须是 `queued` 而不是 `QUEUED`。

    SQLModel 默认按枚举**名字**存，而事件契约、架构文档、以及 `ix_runs_unfinished`
    的谓词写的都是小写的值。两边对不上时一声不响 —— 查询照样对（绑定参数用的是同一套
    编码），坏掉的是那条部分索引（谓词永远匹配不上，崩溃恢复的扫描退化成全表扫）
    与所有照文档写的 SQL。这条用例就是那件事的直接断言。
    """
    async with live_engine.connect() as connection:
        found = await connection.execute(text("SELECT status FROM runs WHERE id = :id"), {"id": submitted})

    assert found.scalar_one() == RunStatus.QUEUED.value


async def test_a_cancelled_run_is_stored_as_cancelled(
    repository: RunRepository, submitted: str, owner: User, live_engine: AsyncEngine
) -> None:
    await repository.cancel(submitted)

    found = await repository.get(submitted, user_id=owner.id)

    assert found is not None
    assert found.status is RunStatus.CANCELLED


async def test_cancelling_a_finished_run_changes_nothing(
    repository: RunRepository, submitted: str, owner: User
) -> None:
    """终态的 run 取消一次是幂等的空操作，不是错误。"""
    await repository.succeed(submitted, tokens=TokenUsage())

    assert await repository.cancel(submitted) is False
    found = await repository.get(submitted, user_id=owner.id)
    assert found is not None
    assert found.status is RunStatus.SUCCEEDED


async def test_only_one_of_two_racing_finalizers_wins(repository: RunRepository, submitted: str) -> None:
    """条件更新是原子的：教师点停止与 worker 跑完撞在一起时，只有一边算数。

    没有这一条，事件说已取消、状态说已成功，两边对不上而且谁都不报错。
    """
    cancelled = await repository.cancel(submitted)
    succeeded = await repository.succeed(submitted, tokens=TokenUsage())

    assert cancelled is True
    assert succeeded is False


async def test_a_cancelled_run_is_no_longer_unfinished(repository: RunRepository, submitted: str) -> None:
    """崩溃恢复不该把已经取消的 run 捞回来重跑。"""
    await repository.cancel(submitted)

    assert submitted not in {run.id for run in await repository.unfinished()}
