"""`runs` 表读写的测试，连真 Postgres。

**核心断言是「换一个仓储实例还查得到」** —— 那就是步骤二验证①：进程重启后
`GET /api/runs/{id}` 仍答得出终态。用替身验不了这个，替身重建之后什么都不剩。

表由 Alembic 建（根 conftest 的 `migrated`），这里不 `create_all`。
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from src.app.agent.config import AgentConfig
from src.app.event.model import RunErrorCode, RunStatus, TokenUsage
from src.app.run.repository import RunRepository, RunStart
from test.conftest import FAKE_HASH
from src.app.thread.repository import Thread
from src.app.user.model import UserRole
from src.app.user.repository import User, UserRepository


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
    assert found.agent_config == AgentConfig()


async def test_a_run_keeps_its_effective_agent_config(
    repository: RunRepository, owner: User, owned_thread: Thread
) -> None:
    run_id = uuid4().hex
    snapshot: dict[str, object] = {"system_prompt": "每句以喵开头"}

    await repository.create(
        run_id=run_id,
        thread_id=owned_thread.id,
        user_id=owner.id,
        agent_config=snapshot,
    )

    found = await repository.get(run_id, user_id=owner.id)
    assert found is not None
    assert found.agent_config.model_dump(exclude_none=True) == snapshot


async def test_a_falsy_non_object_run_snapshot_is_not_treated_as_the_default(
    repository: RunRepository,
    submitted: str,
    owner: User,
    live_engine: AsyncEngine,
) -> None:
    async with live_engine.begin() as connection:
        await connection.execute(
            text("UPDATE runs SET agent_config = CAST(:config AS jsonb) WHERE id = :id"),
            {"config": "[]", "id": submitted},
        )

    try:
        with pytest.raises(ValidationError):
            await repository.get(submitted, user_id=owner.id)
    finally:
        async with live_engine.begin() as connection:
            await connection.execute(
                text("UPDATE runs SET agent_config = NULL WHERE id = :id"),
                {"id": submitted},
            )


async def test_the_history_exposes_each_runs_agent_config(
    repository: RunRepository, owner: User, owned_thread: Thread
) -> None:
    run_id = uuid4().hex
    snapshot: dict[str, object] = {"system_prompt": "这一轮的配置"}
    await repository.create(
        run_id=run_id,
        thread_id=owned_thread.id,
        user_id=owner.id,
        content="一",
        agent_config=snapshot,
    )

    page = await repository.list_by_thread(owned_thread.id, user_id=owner.id)

    detail = next(one for one in page.items if one.id == run_id)
    assert detail.agent_config.model_dump(exclude_none=True) == snapshot


# ------------------------------------------------------------ 开跑：是不是第一次
# 前端拿这个答案决定「要不要把已经显示的对话重置」。答错的代价是一次崩溃恢复之后
# 教师眼前的分析过程被清空重来 —— 而后台其实好好地接着跑。
async def test_live_statuses_reports_only_unfinished_runs(
    repository: RunRepository, submitted: str, owner: User, owned_thread: Thread
) -> None:
    """会话侧栏的「进行中」状态点：还在跑的才算，终态不算，缺席不报。"""
    assert await repository.live_statuses([owned_thread.id], user_id=owner.id) == {owned_thread.id: RunStatus.QUEUED}

    # 走到终态后不再是「进行中」
    tokens = TokenUsage(input_cache_read=0, input_uncached=1, output=2)
    assert await repository.succeed(submitted, tokens=tokens)
    assert await repository.live_statuses([owned_thread.id], user_id=owner.id) == {}

    # 陌生 id 与空列表都不报错
    assert await repository.live_statuses(["never-existed"], user_id=owner.id) == {}
    assert await repository.live_statuses([], user_id=owner.id) == {}


async def test_starting_a_queued_run_is_the_first_time(repository: RunRepository, submitted: str) -> None:
    assert await repository.start(submitted) is RunStart.FIRST


async def test_starting_a_running_run_is_a_resume(repository: RunRepository, submitted: str) -> None:
    """崩溃之后消息重投，状态还停在 `running` —— 这一程是接着跑，不是重来。"""
    await repository.start(submitted)

    assert await repository.start(submitted) is RunStart.RESUMED


async def test_starting_a_run_that_waits_for_approval_is_a_resume(repository: RunRepository, submitted: str) -> None:
    """审批期间的重投同理。"""
    await repository.start(submitted)
    await repository.wait_approval(submitted, tokens=TokenUsage())

    assert await repository.start(submitted) is RunStart.RESUMED


async def test_starting_a_finished_run_is_refused(repository: RunRepository, submitted: str) -> None:
    """已经有终态的 run 再被领走，硬跑下去等于让一次结束的分析又跑一遍，还多花一份 token。"""
    await repository.start(submitted)
    await repository.succeed(submitted, tokens=TokenUsage())

    assert await repository.start(submitted) is RunStart.REFUSED


async def test_starting_a_malformed_id_is_refused(repository: RunRepository) -> None:
    assert await repository.start("not-a-uuid") is RunStart.REFUSED


async def test_a_refused_start_does_not_touch_the_state(repository: RunRepository, submitted: str, owner: User) -> None:
    """两步条件更新都得是原子的：第一步没命中，不能把终态改坏了才发现。"""
    await repository.start(submitted)
    await repository.cancel(submitted)

    await repository.start(submitted)

    found = await repository.get(submitted, user_id=owner.id)
    assert found is not None
    assert found.status is RunStatus.CANCELLED


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
        name=f"stranger-{uuid4().hex[:8]}",
        email=f"{uuid4().hex[:8]}@zuel.edu.cn",
        password_hash=FAKE_HASH,
        role=UserRole.TEACHER,
    )

    assert await repository.get(submitted, user_id=stranger.id) is None


async def test_an_admin_gets_no_special_treatment(
    repository: RunRepository, submitted: str, live_engine: AsyncEngine
) -> None:
    """管理员多的是管账号的能力，不是看别人会话的能力。这一层没有绕过过滤的旁路。"""
    admin = await UserRepository(live_engine).create(
        name=f"admin-{uuid4().hex[:8]}",
        email=f"{uuid4().hex[:8]}@zuel.edu.cn",
        password_hash=FAKE_HASH,
        role=UserRole.ADMIN,
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


async def test_a_run_submitted_just_now_is_held_back_by_the_grace_period(
    repository: RunRepository, submitted: str
) -> None:
    """**宽限期挡的是两次读之间的时间差，不是慢 worker。**

    收割器先读库再读队列。一个 run 若在这两次读之间才被投进队列，库里已经有行、
    队列里还没有它 —— 不设宽限期就会把一次刚提交的分析当场判成孤儿。
    """
    cutoff = datetime.now(UTC) - timedelta(minutes=10)

    assert submitted not in {run.id for run in await repository.unfinished(started_before=cutoff)}


async def test_an_old_run_is_past_the_grace_period(repository: RunRepository, submitted: str) -> None:
    """反面：够老的照样报出来，否则宽限期就成了「永远收割不到」。"""
    long_ago = datetime.now(UTC) + timedelta(hours=1)

    assert submitted in {run.id for run in await repository.unfinished(started_before=long_ago)}


async def test_without_a_cutoff_every_unfinished_run_is_reported(repository: RunRepository, submitted: str) -> None:
    """不给时点就是全量 —— 崩溃恢复那条老路不该被这个新参数改掉行为。"""
    assert submitted in {run.id for run in await repository.unfinished()}


# ------------------------------------------------------------ 会话历史
# 聊天历史的用户那一侧全靠 `content`：事件流里没有承载提问的事件，
# 不落库的话，把一个 run 的事件全部重放一遍也只重建得出 agent 那一半。
async def test_a_run_remembers_the_question(repository: RunRepository, owner: User, owned_thread: Thread) -> None:
    run_id = uuid4().hex
    await repository.create(
        run_id=run_id, thread_id=owned_thread.id, user_id=owner.id, content="按行业分组算年化波动率"
    )

    page = await repository.list_by_thread(owned_thread.id, user_id=owner.id)

    assert [one.content for one in page.items] == ["按行业分组算年化波动率"]


async def test_a_run_without_a_recorded_question_reads_back_empty(
    repository: RunRepository, submitted: str, owner: User, owned_thread: Thread
) -> None:
    """本版之前的 run 在这一列上是空的，那是遗留而不是待回填的空缺。"""
    page = await repository.list_by_thread(owned_thread.id, user_id=owner.id)

    assert [one.content for one in page.items] == [None]


async def test_the_history_gives_the_newest_first(repository: RunRepository, owner: User, owned_thread: Thread) -> None:
    """前端先要最近那几轮，往上滚才翻更早的 —— 与 ix_runs_thread_started 同向。"""
    first, second = uuid4().hex, uuid4().hex
    await repository.create(run_id=first, thread_id=owned_thread.id, user_id=owner.id, content="一")
    await repository.create(run_id=second, thread_id=owned_thread.id, user_id=owner.id, content="二")

    page = await repository.list_by_thread(owned_thread.id, user_id=owner.id)

    assert [one.id for one in page.items] == [second, first]


async def test_the_history_carries_the_outcome_of_each_run(
    repository: RunRepository, submitted: str, owner: User, owned_thread: Thread
) -> None:
    """状态与失败原因要一起给：前端据此决定这一轮显示结果、报错还是重试按钮。"""
    await repository.fail(submitted, code=RunErrorCode.INTERNAL, message="模型断连")

    page = await repository.list_by_thread(owned_thread.id, user_id=owner.id)

    assert page.items[0].status is RunStatus.FAILED
    assert page.items[0].error_code is RunErrorCode.INTERNAL
    assert page.items[0].error_message == "模型断连"


async def test_the_history_carries_the_token_cost(
    repository: RunRepository, submitted: str, owner: User, owned_thread: Thread
) -> None:
    await repository.succeed(submitted, tokens=TokenUsage(input_cache_read=7, input_uncached=11, output=13))

    page = await repository.list_by_thread(owned_thread.id, user_id=owner.id)

    assert page.items[0].tokens == TokenUsage(input_cache_read=7, input_uncached=11, output=13)


async def test_another_users_thread_has_no_history(
    repository: RunRepository, submitted: str, owned_thread: Thread, live_engine: AsyncEngine
) -> None:
    """越权与空会话是同一个结果。过滤在这一层，端点那里没有鉴权判断。"""
    stranger = await UserRepository(live_engine).create(
        name=f"stranger-{uuid4().hex[:8]}",
        email=f"{uuid4().hex[:8]}@zuel.edu.cn",
        password_hash=FAKE_HASH,
        role=UserRole.TEACHER,
    )

    page = await repository.list_by_thread(owned_thread.id, user_id=stranger.id)

    assert page.items == []


async def test_the_history_cursor_walks_every_run_once(
    repository: RunRepository, owner: User, owned_thread: Thread
) -> None:
    created = [uuid4().hex for _ in range(5)]
    for one in created:
        await repository.create(run_id=one, thread_id=owned_thread.id, user_id=owner.id, content=one)

    seen: list[str] = []
    cursor: str | None = None
    while True:
        page = await repository.list_by_thread(owned_thread.id, user_id=owner.id, cursor=cursor, limit=2)
        seen.extend(one.id for one in page.items)
        cursor = page.next_cursor
        if cursor is None:
            break

    assert seen == list(reversed(created))
