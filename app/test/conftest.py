"""需要真 Postgres / 真 Redis 的用例共用的夹具。

**没有替身**：这两样验的是「连得上、写进去、重启后还在」，用假对象顶掉等于把要验的
东西验没了。服务没起时整条用例 skip —— 与沙箱测试同一套路，理由写在 skip 消息里；
CI 那边由 gate workflow 的 services 保证它永远跑得到，不会静默跳过。

连接参数直接取代码里的默认值，不读 `Settings` —— 那要 `.env` 里的 `DEEPSEEK_API_KEY`，
CI 上没有。默认值同时是 compose 与 CI services 起库时用的那一组，两边因此对得上。
"""

from collections.abc import AsyncIterator

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from store.postgres import DEFAULT_DSN, PostgresUnavailableError, create_engine
from store.postgres import check as check_postgres
from store.redis import DEFAULT_URL, RedisUnavailableError, create_client
from store.redis import check as check_redis

SKIP_POSTGRES = "没有可用的 Postgres：docker compose -f deploy/compose.yml up -d postgres"
SKIP_REDIS = "没有可用的 Redis：docker compose -f deploy/compose.yml up -d redis"


@pytest.fixture
async def live_engine() -> AsyncIterator[AsyncEngine]:
    created = create_engine(DEFAULT_DSN)
    try:
        await check_postgres(created)
    except PostgresUnavailableError:
        await created.dispose()
        pytest.skip(SKIP_POSTGRES)
    try:
        yield created
    finally:
        await created.dispose()


@pytest.fixture
async def live_cache() -> AsyncIterator[Redis]:
    created = create_client(DEFAULT_URL)
    try:
        await check_redis(created)
    except RedisUnavailableError:
        await created.aclose()
        pytest.skip(SKIP_REDIS)
    try:
        yield created
    finally:
        await created.aclose()
