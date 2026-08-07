"""登录态的测试，连真 Redis。

用真 Redis 而不是替身：要验的就是「令牌存进去了、TTL 推得动、删了就不认」，
拿假对象顶掉等于把这三件事全验没了。
"""

import pytest
from redis.asyncio import Redis

from auth.session import KEY_PREFIX, Session, SessionStore
from user.model import UserRole

SHORT_TTL_SECOND = 60
LONG_TTL_SECOND = 3600


@pytest.fixture
def store(live_cache: Redis) -> SessionStore:
    return SessionStore(live_cache, ttl_second=SHORT_TTL_SECOND)


def _session() -> Session:
    return Session(user_id="u-1", name="王老师", role=UserRole.TEACHER)


async def test_an_issued_token_resolves_back_to_the_identity(store: SessionStore) -> None:
    token = await store.issue(_session())

    assert await store.resolve(token) == _session()


async def test_every_token_is_different(store: SessionStore) -> None:
    """两端同时登录是允许的，但两端的令牌不能是同一个 —— 否则登出一端就踢掉另一端。"""
    assert await store.issue(_session()) != await store.issue(_session())


async def test_an_unknown_token_resolves_to_nothing(store: SessionStore) -> None:
    assert await store.resolve("从来没发过这个") is None


async def test_a_revoked_token_stops_working(store: SessionStore) -> None:
    token = await store.issue(_session())

    await store.revoke(token)

    assert await store.resolve(token) is None


async def test_revoking_an_unknown_token_is_harmless(store: SessionStore) -> None:
    """登出会被点两次、也会在 Cookie 早就过期之后才点。"""
    await store.revoke("从来没发过这个")


async def test_resolving_pushes_the_expiry_back(live_cache: Redis) -> None:
    """滑动过期：天天用的人不该被踢下线。

    先用短 TTL 发一个，再用长 TTL 的实例去 resolve 一次 —— 键上的 TTL 必须变成长的那个。
    直接等它过期要等一分钟，而这条验的是「续没续」，不是「过没过」。
    """
    token = await SessionStore(live_cache, ttl_second=SHORT_TTL_SECOND).issue(_session())

    await SessionStore(live_cache, ttl_second=LONG_TTL_SECOND).resolve(token)

    assert await live_cache.ttl(f"{KEY_PREFIX}{token}") > SHORT_TTL_SECOND


async def test_an_expired_token_resolves_to_nothing(live_cache: Redis) -> None:
    """键到期之后就是「没登录」，与从没发过是同一个结果。"""
    store = SessionStore(live_cache, ttl_second=SHORT_TTL_SECOND)
    token = await store.issue(_session())
    await live_cache.delete(f"{KEY_PREFIX}{token}")

    assert await store.resolve(token) is None
