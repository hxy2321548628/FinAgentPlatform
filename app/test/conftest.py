"""需要真 Postgres / 真 Redis 的用例共用的夹具。

**没有替身**：这两样验的是「连得上、写进去、重启后还在」，用假对象顶掉等于把要验的
东西验没了。服务没起时整条用例 skip —— 与沙箱测试同一套路，理由写在 skip 消息里；
CI 那边由 gate workflow 的 services 保证它永远跑得到，不会静默跳过。

连接参数走 `StoreSettings`，与 Alembic 读的是同一份 —— 各写各的默认值会出现
「测试连 A 库、迁移建 B 库」，而那种故障不报错，只是表「不见了」。
"""

from collections.abc import AsyncIterator
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from config import StoreSettings
from store.postgres import PostgresUnavailableError, create_engine
from store.postgres import check as check_postgres
from store.redis import RedisUnavailableError, create_client
from store.redis import check as check_redis

SETTINGS = StoreSettings()
ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"

# 探活用。要短：连不上时每条用例都会等它一次
PROBE_TIMEOUT_SECOND = 2

SKIP_POSTGRES = "没有可用的 Postgres：docker compose -f deploy/compose.yml up -d postgres"
SKIP_REDIS = "没有可用的 Redis：docker compose -f deploy/compose.yml up -d redis"


@pytest.fixture(scope="session")
def migrated() -> None:
    """把库迁到最新。

    **测试也走 Alembic，不另起一条 `create_all`** —— 两条路都能建表时，
    它们迟早会分叉，而分叉的症状是「本地全绿、上线缺列」。
    """
    try:
        with psycopg.connect(SETTINGS.postgres_conninfo(), connect_timeout=PROBE_TIMEOUT_SECOND):
            pass
    except psycopg.Error:
        pytest.skip(SKIP_POSTGRES)
    command.upgrade(Config(str(ALEMBIC_INI)), "head")


@pytest.fixture
async def live_engine(migrated: None) -> AsyncIterator[AsyncEngine]:
    created = create_engine(SETTINGS.postgres_dsn())
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
    created = create_client(SETTINGS.redis_url)
    try:
        await check_redis(created)
    except RedisUnavailableError:
        await created.aclose()
        pytest.skip(SKIP_REDIS)
    try:
        yield created
    finally:
        await created.aclose()
