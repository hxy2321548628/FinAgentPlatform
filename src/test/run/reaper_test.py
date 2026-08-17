"""孤儿 run 的收割，连真 Postgres。

**这一组的重心全在「什么不该被收割」。** 误判的代价是不对称的：漏掉一个孤儿只是它
多躺一会儿，而错杀一个正在跑的 run 会把教师烧了几十万 token 的分析判成失败 ——
而且那一刀砍下去没有任何回头路。
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.event.model import Event, EventType, RunErrorCode, RunStatus, TokenUsage
from app.run.log import LoggedEvent
from app.run.reaper import orphaned, sweep
from app.run.repository import Run, RunRepository
from app.thread.repository import Thread
from app.user.repository import User

# 宽限期取 0：测试里造出来的 run 都是「刚提交的」，留宽限期的话每一条都会被挡住。
# 宽限期本身由 test_a_run_submitted_within_the_grace_period_is_left_alone 单独验
NO_GRACE_MINUTE = 0


class FakeQueue:
    """队列替身，只回答「还有谁在里面」。"""

    def __init__(self, in_flight: set[str] | None = None) -> None:
        self._in_flight = in_flight or set()

    async def in_flight(self) -> set[str]:
        return self._in_flight


class LosingRepository:
    """条件更新永远落空的仓储：模拟「读到它还活着，动手之前它已经走到终态」。"""

    def __init__(self, run: Run) -> None:
        self._run = run

    async def unfinished(self, *, started_before: datetime | None = None) -> list[Run]:
        return [self._run]

    async def fail(self, run_id: str, *, code: RunErrorCode, message: str) -> bool:
        return False


class FakeLog:
    """事件日志替身，把收到的事件留下来供断言。"""

    def __init__(self) -> None:
        self.appended: list[Event] = []

    async def append(self, event: Event) -> LoggedEvent:
        self.appended.append(event)
        return LoggedEvent(id=f"{len(self.appended)}-0", event=event)


@pytest.fixture
def repository(live_engine: AsyncEngine) -> RunRepository:
    return RunRepository(live_engine)


@pytest.fixture
def log() -> FakeLog:
    return FakeLog()


async def _live(
    engine: AsyncEngine,
    owner: User,
    thread: Thread,
    *,
    running: bool = False,
    started: datetime | None = None,
) -> str:
    """造一个还活着的 run，可以指定它是什么时候提交的。"""
    run_id = uuid4().hex
    repository = RunRepository(engine)
    await repository.create(run_id=run_id, thread_id=thread.id, user_id=owner.id)
    if running:
        await repository.start(run_id)
    if started is not None:
        # 「提交于一小时前」没有公开入口造得出来，只能直接改那一列
        async with engine.begin() as connection:
            await connection.execute(
                text("UPDATE runs SET started_at = :moment WHERE id = :run_id"),
                {"moment": started, "run_id": run_id},
            )
    return run_id


# ------------------------------------------------------------------ 什么不该被收割
async def test_a_run_the_queue_still_holds_is_left_alone(
    live_engine: AsyncEngine, repository: RunRepository, owner: User, owned_thread: Thread, log: FakeLog
) -> None:
    """**最重要的一条。** 队列里还有它，就说明有 worker 正拿着它跑，或者它还在排队。

    断言只认自己造的那一条，不看总数：测试库是共享的，别的用例留下的未完成 run
    同样会被这一次清扫收走，用总数断言的话这条用例的真假取决于它跑在第几个。
    """
    run_id = await _live(live_engine, owner, owned_thread, running=True)

    await sweep(repository, FakeQueue({run_id}), log, grace_minute=NO_GRACE_MINUTE)

    assert run_id not in {one.run_id for one in log.appended}
    found = await repository.get(run_id, user_id=owner.id)
    assert found is not None
    assert found.status is RunStatus.RUNNING


async def test_a_run_submitted_within_the_grace_period_is_left_alone(
    live_engine: AsyncEngine, repository: RunRepository, owner: User, owned_thread: Thread, log: FakeLog
) -> None:
    """收割器先读库再读队列。刚提交的 run 可能正卡在这两步之间，队列里还没有它。"""
    run_id = await _live(live_engine, owner, owned_thread)

    await sweep(repository, FakeQueue(), log, grace_minute=10)

    assert run_id not in {one.run_id for one in log.appended}


async def test_a_finished_run_is_not_reaped(
    live_engine: AsyncEngine, repository: RunRepository, owner: User, owned_thread: Thread, log: FakeLog
) -> None:
    """已经有终态的不在扫描范围里 —— 它既不在队列里，也不该被再动一次。"""
    run_id = await _live(live_engine, owner, owned_thread, running=True)
    await repository.succeed(run_id, tokens=TokenUsage())

    await sweep(repository, FakeQueue(), log, grace_minute=NO_GRACE_MINUTE)

    assert run_id not in {one.run_id for one in log.appended}


# ------------------------------------------------------------------ 什么该被收割
async def test_a_run_the_queue_lost_is_reaped(
    live_engine: AsyncEngine, repository: RunRepository, owner: User, owned_thread: Thread, log: FakeLog
) -> None:
    """库里还活着，队列里却没有它 —— 没有任何东西会再碰它，这就是孤儿。"""
    run_id = await _live(live_engine, owner, owned_thread, running=True)

    found = await orphaned(repository, FakeQueue(), grace_minute=NO_GRACE_MINUTE)

    assert run_id in found


async def test_the_orphan_ends_up_failed_not_cancelled(
    live_engine: AsyncEngine, repository: RunRepository, owner: User, owned_thread: Thread, log: FakeLog
) -> None:
    """**是失败不是取消。** 没有人取消它，是平台把它弄丢了 —— 说成取消是在替自己遮掩。"""
    run_id = await _live(live_engine, owner, owned_thread, running=True)

    await sweep(repository, FakeQueue(), log, grace_minute=NO_GRACE_MINUTE)

    found = await repository.get(run_id, user_id=owner.id)
    assert found is not None
    assert found.status is RunStatus.FAILED


async def test_the_orphan_is_reported_as_retryable(
    live_engine: AsyncEngine, repository: RunRepository, owner: User, owned_thread: Thread, log: FakeLog
) -> None:
    """`retryable` 就是这个项目「重不重试由人决定」的落点：前端据此显示重试按钮。

    平台自己重投是不行的 —— 那是自动重试，而且多副本下会撞出双重执行。
    """
    run_id = await _live(live_engine, owner, owned_thread, running=True)

    await sweep(repository, FakeQueue(), log, grace_minute=NO_GRACE_MINUTE)

    failed = [one for one in log.appended if one.run_id == run_id]
    assert len(failed) == 1
    assert failed[0].type is EventType.RUN_FAILED
    assert failed[0].data.code is RunErrorCode.ORPHANED
    assert failed[0].data.retryable is True


async def test_a_queued_orphan_is_reaped_too(
    live_engine: AsyncEngine, repository: RunRepository, owner: User, owned_thread: Thread, log: FakeLog
) -> None:
    """卡在 `queued` 的与卡在 `running` 的是同一种病：消息没了，状态没人改。"""
    run_id = await _live(live_engine, owner, owned_thread)
    async with live_engine.begin() as connection:
        await connection.execute(
            text("UPDATE runs SET started_at = :moment WHERE id = :run_id"),
            {"moment": datetime.now(UTC) - timedelta(hours=1), "run_id": run_id},
        )

    await sweep(repository, FakeQueue(), log, grace_minute=10)

    assert run_id in {one.run_id for one in log.appended}


# ------------------------------------------------------------------ 重跑与竞态
async def test_sweeping_twice_reaps_nothing_the_second_time(
    live_engine: AsyncEngine, repository: RunRepository, owner: User, owned_thread: Thread, log: FakeLog
) -> None:
    """定时任务要可重跑 —— 第二次什么都不该发生，靠的是条件更新而不是记账。"""
    run_id = await _live(live_engine, owner, owned_thread, running=True)
    first = await sweep(repository, FakeQueue(), log, grace_minute=NO_GRACE_MINUTE)
    assert run_id in {one.run_id for one in log.appended}
    assert first >= 1

    second = await sweep(repository, FakeQueue(), log, grace_minute=NO_GRACE_MINUTE)

    assert second == 0


async def test_a_run_that_reached_a_terminal_state_first_gets_no_event(log: FakeLog) -> None:
    """读到它还活着、动手之前它跑完了 —— 那一刻推 `run.failed` 会让一次成功的分析显示成失败。

    挡住这件事的是 `fail()` 的条件更新：**没改成就不推事件**。

    **用替身而不是真库**：真库里那一刻的 run 已经是终态，`unfinished()` 根本不会
    返回它，于是那道守卫压根走不到 —— 第一版就是这么写的，把守卫整个删掉测试照样绿。
    要验的是「仓储说没改成时收割器怎么办」，那就得让仓储说没改成。
    """
    losing = LosingRepository(Run(id=uuid4().hex, thread_id=uuid4().hex, status=RunStatus.RUNNING))

    reaped = await sweep(losing, FakeQueue(), log, grace_minute=NO_GRACE_MINUTE)

    assert reaped == 0
    assert log.appended == []
