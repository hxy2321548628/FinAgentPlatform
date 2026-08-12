"""接口限流的测试，连真 Redis。

用真 Redis 而不是替身：要验的正是「多个 api 副本共用同一份计数」，
进程内的假对象把这件事验没了。
"""

import time

import pytest
from redis.asyncio import Redis

from quota.rate import KEY_PREFIX, RateLimiter

LIMIT = 3
WINDOW_SECOND = 60

# 窗口短到用例等得起，但仍明显长于一次 Redis 往返
BRIEF_WINDOW_SECOND = 1


@pytest.fixture
def limiter(live_cache: Redis) -> RateLimiter:
    return RateLimiter(live_cache, limit=LIMIT, window_second=WINDOW_SECOND)


async def test_requests_below_the_limit_pass(limiter: RateLimiter) -> None:
    for _ in range(LIMIT):
        assert await limiter.allow("甲") is True


async def test_the_one_over_the_limit_is_refused(limiter: RateLimiter) -> None:
    for _ in range(LIMIT):
        await limiter.allow("甲")

    assert await limiter.allow("甲") is False


async def test_a_refused_request_does_not_eat_a_slot(live_cache: Redis, limiter: RateLimiter) -> None:
    """先数再记：被拒的那次若也占一个名额，超限之后每次尝试都在给自己续命，窗口永远清不空。"""
    for _ in range(LIMIT + 5):
        await limiter.allow("甲")

    assert await live_cache.zcard(f"{KEY_PREFIX}甲") == LIMIT


async def test_two_keys_are_counted_apart(limiter: RateLimiter) -> None:
    """一个人打满了，不能把别人一起拦住。"""
    for _ in range(LIMIT):
        await limiter.allow("甲")

    assert await limiter.allow("乙") is True


async def test_the_window_slides(live_cache: Redis) -> None:
    """固定窗口在接缝处允许两倍的量 —— 59 秒打满一轮、61 秒再打满一轮。滑动窗口不会。"""
    limiter = RateLimiter(live_cache, limit=LIMIT, window_second=BRIEF_WINDOW_SECOND)
    for _ in range(LIMIT):
        await limiter.allow("甲")
    assert await limiter.allow("甲") is False

    time.sleep(BRIEF_WINDOW_SECOND + 0.2)

    assert await limiter.allow("甲") is True


async def test_two_hits_in_the_same_instant_are_both_counted(live_cache: Redis) -> None:
    """成员必须唯一：同一毫秒里的两次若覆盖成一条，窗口里就少算了一次。"""
    limiter = RateLimiter(live_cache, limit=LIMIT, window_second=WINDOW_SECOND)

    await limiter.allow("甲")
    await limiter.allow("甲")

    assert await live_cache.zcard(f"{KEY_PREFIX}甲") == 2


async def test_the_key_expires_so_idle_users_leave_nothing_behind(live_cache: Redis, limiter: RateLimiter) -> None:
    await limiter.allow("甲")

    assert 0 < await live_cache.ttl(f"{KEY_PREFIX}甲") <= WINDOW_SECOND
