"""取消标志的测试，连真 Redis。

它是 api 与 worker 之间唯一的取消通道，两边跑在不同的进程里 ——
用替身验等于把「跨进程」这件事验没了。
"""

from uuid import uuid4

import pytest
from redis.asyncio import Redis

from run.cancel import KEY_PREFIX, CancelFlag

SHORT_TTL_SECOND = 60


@pytest.fixture
def flag(live_cache: Redis) -> CancelFlag:
    return CancelFlag(live_cache, ttl_second=SHORT_TTL_SECOND)


async def test_a_fresh_run_has_no_flag(flag: CancelFlag) -> None:
    assert await flag.is_raised(uuid4().hex) is False


async def test_a_raised_flag_is_visible(flag: CancelFlag) -> None:
    run_id = uuid4().hex

    await flag.raise_flag(run_id)

    assert await flag.is_raised(run_id) is True


async def test_another_run_is_not_affected(flag: CancelFlag) -> None:
    """标志按 run 分。搞混的话，取消一次会把这个会话之后的每一次分析都停掉。"""
    await flag.raise_flag(uuid4().hex)

    assert await flag.is_raised(uuid4().hex) is False


async def test_raising_twice_is_harmless(flag: CancelFlag) -> None:
    """教师会连点两下「停止」。"""
    run_id = uuid4().hex

    await flag.raise_flag(run_id)
    await flag.raise_flag(run_id)

    assert await flag.is_raised(run_id) is True


async def test_a_cleared_flag_is_gone(flag: CancelFlag) -> None:
    run_id = uuid4().hex
    await flag.raise_flag(run_id)

    await flag.clear(run_id)

    assert await flag.is_raised(run_id) is False


async def test_the_flag_expires_by_itself(live_cache: Redis, flag: CancelFlag) -> None:
    """标志不会永远堆着。TTL 要长于一个 run 可能的最长寿命 —— 审批能挂 24 小时。"""
    run_id = uuid4().hex

    await flag.raise_flag(run_id)

    assert 0 < await live_cache.ttl(f"{KEY_PREFIX}{run_id}") <= SHORT_TTL_SECOND
