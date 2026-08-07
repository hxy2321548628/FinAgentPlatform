"""Redis 接入的测试。"""

import pytest
from redis.asyncio import Redis

from store.redis import RedisUnavailableError, check, create_client

# 一个不会有人监听的端口
DEAD_URL = "redis://127.0.0.1:1/0"


async def test_check_raises_when_redis_is_unreachable() -> None:
    dead = create_client(DEAD_URL)
    try:
        with pytest.raises(RedisUnavailableError):
            await check(dead)
    finally:
        await dead.aclose()


async def test_check_passes_against_a_live_redis(live_cache: Redis) -> None:
    await check(live_cache)


async def test_the_client_decodes_replies_to_text(live_cache: Redis) -> None:
    """事件信封是 JSON 文本。客户端不解码的话，每个调用方都得自己 decode 一遍。"""
    key = "zuel:test:decode"
    await live_cache.set(key, "行业分布")
    try:
        assert await live_cache.get(key) == "行业分布"
    finally:
        await live_cache.delete(key)
