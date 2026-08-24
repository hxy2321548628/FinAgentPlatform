"""用量统计的测试，连真 Postgres。

**最核心的一条是「`cache_read` 不计入」**（步骤三验证②）。按 input 总数扣会高估约
1.6 倍，而且方向性地惩罚长会话 —— 会话越长命中率越高、边际成本越低，按总数扣却扣得
越狠。扣错方向比扣错数值严重得多，因此这一条单独立一个用例。
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.event.model import RunStatus, TokenUsage
from app.memory.job import MemoryJobRepository, MemoryUsage, MemoryUsageStage
from app.quota.usage import DEFAULT_RESET_TIMEZONE, RunUsage, day_start, next_reset
from app.run.repository import RunRepository
from app.thread.repository import Thread
from app.user.repository import User

# 一次高命中的调用：input 总数 10000，其中 9000 命中 cache。
# 按总数扣是 10000，按未命中扣是 1000 —— 这两个数差一个数量级，断言不会含糊
CACHED = TokenUsage(input_cache_read=9_000, input_uncached=1_000, output=500)


@pytest.fixture
def usage(live_engine: AsyncEngine) -> RunUsage:
    return RunUsage(live_engine)


@pytest.fixture
def repository(live_engine: AsyncEngine) -> RunRepository:
    return RunRepository(live_engine)


async def _finished(repository: RunRepository, owner: User, thread: Thread, tokens: TokenUsage) -> str:
    run_id = uuid4().hex
    await repository.create(run_id=run_id, thread_id=thread.id, user_id=owner.id)
    await repository.succeed(run_id, tokens=tokens)
    return run_id


async def test_a_fresh_user_has_burned_nothing(usage: RunUsage, owner: User) -> None:
    assert await usage.token_today(owner.id) == 0


async def test_cache_hits_are_not_charged(
    usage: RunUsage, repository: RunRepository, owner: User, owned_thread: Thread
) -> None:
    """扣的是未命中那部分加 output，命中的 9000 一个都不算。"""
    await _finished(repository, owner, owned_thread, CACHED)

    assert await usage.token_today(owner.id) == CACHED.input_uncached + CACHED.output


async def test_the_output_weight_is_applied(
    live_engine: AsyncEngine, repository: RunRepository, owner: User, owned_thread: Thread
) -> None:
    """权重目前是 1，但机制得在 —— 拿到真实价目表时改的是配置，不是这段代码。"""
    await _finished(repository, owner, owned_thread, CACHED)

    weighted = await RunUsage(live_engine, output_weight=3).token_today(owner.id)

    assert weighted == CACHED.input_uncached + CACHED.output * 3


async def test_usage_adds_up_across_runs(
    usage: RunUsage, repository: RunRepository, owner: User, owned_thread: Thread
) -> None:
    await _finished(repository, owner, owned_thread, CACHED)
    await _finished(repository, owner, owned_thread, CACHED)

    assert await usage.token_today(owner.id) == 2 * (CACHED.input_uncached + CACHED.output)


async def test_async_memory_usage_is_charged_but_selector_is_not_counted_twice(
    live_engine: AsyncEngine,
    usage: RunUsage,
    repository: RunRepository,
    owner: User,
    owned_thread: Thread,
) -> None:
    run_id = await _finished(repository, owner, owned_thread, CACHED)
    memory = MemoryJobRepository(live_engine)
    extra = TokenUsage(input_cache_read=900, input_uncached=100, output=50)
    await memory.record_usage(
        MemoryUsage(
            run_id=run_id,
            thread_id=owned_thread.id,
            stage=MemoryUsageStage.SELECTOR,
            model="aux",
            tokens=extra,
            cost_yuan=0.1,
            duration_ms=1,
            included_in_run=True,
        )
    )
    await memory.record_usage(
        MemoryUsage(
            run_id=run_id,
            thread_id=owned_thread.id,
            stage=MemoryUsageStage.EXTRACTOR,
            model="aux",
            tokens=extra,
            cost_yuan=0.1,
            duration_ms=1,
        )
    )

    assert await usage.token_today(owner.id) == (
        CACHED.input_uncached + CACHED.output + extra.input_uncached + extra.output
    )


async def test_another_users_burn_is_not_counted(
    usage: RunUsage, repository: RunRepository, owner: User, owned_thread: Thread
) -> None:
    """配额是 per-user 的。数错人的话，一个重度用户会把全院都锁死。"""
    await _finished(repository, owner, owned_thread, CACHED)

    assert await usage.token_today(uuid4().hex) == 0


async def test_yesterdays_burn_does_not_count_today(
    usage: RunUsage, repository: RunRepository, owner: User, owned_thread: Thread
) -> None:
    """每日 0 点重置 —— 这与 QUOTA_EXCEEDED 那句「明日 0 点重置」是同一件事。"""
    await _finished(repository, owner, owned_thread, CACHED)

    tomorrow = datetime.now(UTC) + timedelta(days=1)

    assert await usage.token_today(owner.id, now=tomorrow) == 0


async def test_a_malformed_user_id_burns_nothing_instead_of_raising(usage: RunUsage) -> None:
    assert await usage.token_today("这不是一个 uuid") == 0


# ------------------------------------------------------------------ 并发
async def test_a_queued_run_occupies_a_slot(
    usage: RunUsage, repository: RunRepository, owner: User, owned_thread: Thread
) -> None:
    await repository.create(run_id=uuid4().hex, thread_id=owned_thread.id, user_id=owner.id)

    assert await usage.active_run(owner.id) == 1


async def test_a_running_run_occupies_a_slot(
    usage: RunUsage, repository: RunRepository, owner: User, owned_thread: Thread
) -> None:
    run_id = uuid4().hex
    await repository.create(run_id=run_id, thread_id=owned_thread.id, user_id=owner.id)
    await repository.start(run_id)

    assert await usage.active_run(owner.id) == 1


async def test_a_finished_run_gives_its_slot_back(
    usage: RunUsage, repository: RunRepository, owner: User, owned_thread: Thread
) -> None:
    await _finished(repository, owner, owned_thread, CACHED)

    assert await usage.active_run(owner.id) == 0


async def test_only_the_two_active_states_occupy_a_slot() -> None:
    """并发配额限制的是**资源占用**。

    `waiting_approval`（步骤五）与 `cancelled`（步骤四）落地时都不该进这个集合 ——
    等人确认期间既不占 worker 也不占沙箱，算进来的话教师忘了点确认就把自己锁死一整天。
    """
    from app.quota.usage import ACTIVE_STATUS

    assert set(ACTIVE_STATUS) == {RunStatus.QUEUED, RunStatus.RUNNING}


async def test_another_users_runs_do_not_fill_my_slots(
    usage: RunUsage, repository: RunRepository, owner: User, owned_thread: Thread
) -> None:
    await repository.create(run_id=uuid4().hex, thread_id=owned_thread.id, user_id=owner.id)

    assert await usage.active_run(uuid4().hex) == 0


# ------------------------------------------------------------------ 重置时刻
BEIJING = ZoneInfo("Asia/Shanghai")


def test_the_day_starts_at_midnight_in_the_configured_zone() -> None:
    """15:30 UTC 已经是北京时间第二天 23:30，那一天的起点是北京的 8 月 8 日零点。"""
    moment = datetime(2026, 8, 8, 15, 30, tzinfo=UTC)

    assert day_start(moment, zone=BEIJING) == datetime(2026, 8, 8, tzinfo=BEIJING)


def test_the_day_boundary_is_not_utc_midnight() -> None:
    """**这一条就是那个 bug 的守门人。**

    按 UTC 切的话，北京时间 8 月 9 日凌晨 1 点会被算成「还是 8 月 8 日」——
    教师那边日历已经翻页，配额却要再等 8 小时才重置，而提示语印出来的是「00:00」。
    """
    just_after_midnight = datetime(2026, 8, 9, 1, 0, tzinfo=BEIJING)

    assert day_start(just_after_midnight, zone=BEIJING) == datetime(2026, 8, 9, tzinfo=BEIJING)
    assert day_start(just_after_midnight, zone=UTC) == datetime(2026, 8, 8, tzinfo=UTC)


def test_the_next_reset_is_tomorrow_midnight() -> None:
    """提示语里那个时刻要与真正的重置对得上，否则教师会在还没重置时白来一趟。"""
    moment = datetime(2026, 8, 8, 15, 30, tzinfo=UTC)

    assert next_reset(moment, zone=BEIJING) == datetime(2026, 8, 9, tzinfo=BEIJING)


def test_the_reset_hint_reads_as_midnight_not_as_the_process_timezone() -> None:
    """**提示语不能再 `astimezone()` 一次。**

    容器里 `TZ` 是 UTC，那一步什么都不转，于是「00:00 重置」实际是北京时间早上八点。
    从这一层拿到的时刻必须已经在该显示的那个时区上，直接 `strftime` 就对。
    """
    moment = datetime(2026, 8, 8, 15, 30, tzinfo=UTC)

    shown = next_reset(moment, zone=BEIJING).strftime("%m-%d %H:%M")

    assert shown == "08-09 00:00"


def test_the_default_zone_is_the_one_the_teachers_live_in() -> None:
    """「每天 0 点重置」这句话是说给教师听的，它必须在教师的钟上成立。"""
    assert DEFAULT_RESET_TIMEZONE == "Asia/Shanghai"
