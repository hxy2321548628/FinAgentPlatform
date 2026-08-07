"""需要真 Postgres / 真 Redis 的用例共用的夹具。

**没有替身**：这两样验的是「连得上、写进去、重启后还在」，用假对象顶掉等于把要验的
东西验没了。服务没起时整条用例 skip —— 与沙箱测试同一套路，理由写在 skip 消息里；
CI 那边由 gate workflow 的 services 保证它永远跑得到，不会静默跳过。

连接参数走 `StoreSettings`，与 Alembic 读的是同一份 —— 各写各的默认值会出现
「测试连 A 库、迁移建 B 库」，而那种故障不报错，只是表「不见了」。
"""

import contextlib
import json
import logging
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from io import StringIO
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from psycopg import sql
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from config import StoreSettings
from log import JsonFormatter
from store.postgres import DRIVER, NATIVE_DRIVER, PostgresUnavailableError, build_dsn, create_engine
from store.postgres import check as check_postgres
from store.redis import RedisUnavailableError, create_client
from store.redis import check as check_redis
from thread.repository import Thread, ThreadRepository
from user.model import UserRole
from user.repository import User, UserRepository

SETTINGS = StoreSettings()
ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"

# 探活用。要短：连不上时每条用例都会等它一次
PROBE_TIMEOUT_SECOND = 2

# 测试专用的 Redis 逻辑库。**不能用业务那个 0 号库** —— 用例之间要清空，
# 而清空会把开发机上正在跑的 run 的事件一起冲掉
TEST_REDIS_DATABASE = 15

# 测试专用的 Postgres 库，与上面同一个理由。共用业务库时测试数据会一行行混进业务表，
# 而混进去之后就再也分不出哪些行是测试留下的 —— 每加一张表混得更多一批。
# 库不存在时由 `migrated` 自己建，因此新机器不必先手工 createdb
TEST_POSTGRES_DATABASE = "zuel_test"

SKIP_POSTGRES = "没有可用的 Postgres：docker compose -f deploy/compose.yml up -d postgres"
SKIP_REDIS = "没有可用的 Redis：docker compose -f deploy/compose.yml up -d redis"

# 建账号的夹具只需要一个形状对的串。真的哈希在 auth 那边的用例里算
FAKE_HASH = "$argon2id$v=19$m=8,t=1,p=1$假的但形状对"


def store_dsn(driver: str, *, database: str = TEST_POSTGRES_DATABASE) -> str:
    """拼一条指向测试库的连接串。

    连接参数取自 `StoreSettings`，只把库名换掉 —— 各写各的默认值会出现
    「测试连 A 库、迁移建 B 库」，而那种故障不报错，只是表「不见了」。

    Args:
        driver: 协议前缀，SQLAlchemy 与原生 psycopg 认的不是同一个。
        database: 库名。

    Returns:
        可直接交给引擎或 psycopg 的 DSN。
    """
    return build_dsn(
        host=SETTINGS.postgres_host,
        port=SETTINGS.postgres_port,
        user=SETTINGS.postgres_user,
        password=SETTINGS.postgres_password.get_secret_value(),
        database=database,
        driver=driver,
    )


TEST_POSTGRES_DSN = store_dsn(DRIVER)
TEST_POSTGRES_CONNINFO = store_dsn(NATIVE_DRIVER)


def alembic_config(dsn: str) -> Config:
    """指到某个库的 alembic 配置。

    Args:
        dsn: 目标库的连接串。

    Returns:
        可交给 `command.upgrade` 的配置。
    """
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", dsn)
    return config


@contextmanager
def maintenance() -> Iterator[psycopg.Connection[tuple[object, ...]]]:
    """连到业务库，只为了下一句 CREATE / DROP DATABASE。

    建库不能在要建的那个库里下，得先连上另一个已经存在的库。业务库一定在
    （compose 起 postgres 时就建了），且这条连接除了那一句什么都不做。

    Yields:
        自动提交的连接 —— CREATE DATABASE 不能在事务里跑。
    """
    with psycopg.connect(
        SETTINGS.postgres_conninfo(), connect_timeout=PROBE_TIMEOUT_SECOND, autocommit=True
    ) as connection:
        yield connection


def ensure_database(name: str) -> None:
    """建一个库，已经有了就当无事发生。

    Args:
        name: 库名。
    """
    with maintenance() as connection, contextlib.suppress(psycopg.errors.DuplicateDatabase):
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))


def drop_database(name: str) -> None:
    """删掉一个库，连同还连着它的连接。

    Args:
        name: 库名。
    """
    with maintenance() as connection:
        connection.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))


@contextmanager
def json_log(name: str) -> Iterator[list[dict[str, object]]]:
    """收下某个 logger 的输出，按真正的 JSON formatter 渲染后解析。

    **不能用 `caplog`**：`run_id` / `thread_id` 是 formatter 从 contextvars 里取的，
    record 上并没有这两个字段，而验收脚本用 `jq` 读的正是渲染之后的那一行。

    Args:
        name: 要收的 logger 名。

    Yields:
        一个列表，**退出上下文之后**才装上解析好的日志行。
    """
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger(name)
    level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    parsed: list[dict[str, object]] = []
    try:
        yield parsed
    finally:
        logger.removeHandler(handler)
        logger.setLevel(level)
        parsed.extend(json.loads(one) for one in stream.getvalue().splitlines())


@pytest.fixture(scope="session")
def migrated() -> None:
    """把**测试库**迁到最新，库不存在就先建。

    **测试也走 Alembic，不另起一条 `create_all`** —— 两条路都能建表时，
    它们迟早会分叉，而分叉的症状是「本地全绿、上线缺列」。
    """
    try:
        ensure_database(TEST_POSTGRES_DATABASE)
    except psycopg.Error:
        pytest.skip(SKIP_POSTGRES)
    command.upgrade(alembic_config(TEST_POSTGRES_DSN), "head")


@pytest.fixture
async def live_engine(migrated: None) -> AsyncIterator[AsyncEngine]:
    created = create_engine(TEST_POSTGRES_DSN)
    try:
        await check_postgres(created)
    except PostgresUnavailableError:
        await created.dispose()
        pytest.skip(SKIP_POSTGRES)
    # 体检那条连接要扔掉，见下面 live_cache 里同一个理由
    await created.dispose()
    try:
        yield created
    finally:
        await created.dispose()


@pytest.fixture
async def owner(live_engine: AsyncEngine) -> User:
    """一个真的账号。

    `threads.user_id` 与 `runs.user_id` 都有外键，凭空编一个 uuid 已经写不进去了 ——
    这正是隔离做在数据层的副作用：无主的数据在库那一层就存不下来。
    """
    return await UserRepository(live_engine).create(
        name=f"owner-{uuid4().hex[:8]}", password_hash=FAKE_HASH, role=UserRole.TEACHER
    )


@pytest.fixture
async def owned_thread(live_engine: AsyncEngine, owner: User) -> Thread:
    """一个真的会话，主人是 `owner`。"""
    return await ThreadRepository(live_engine).create(user_id=owner.id)


@pytest.fixture
async def live_cache() -> AsyncIterator[Redis]:
    """清空过的测试库。

    **每条用例开头清一次**：事件流按 run 分键，而用例里的 run id 有写死的，
    不清就会读到上一条用例留下的事件。清的是 15 号库，与业务数据分家。

    **清完要断开连接池**：asyncio 的连接绑在创建它的事件循环上，而 `TestClient`
    把应用跑在另一个线程的另一个循环里。把这里建出来的连接留在池子里，
    应用那一侧取到它就会挂死在读上 —— 症状是超时，不指向事件循环。
    """
    created = create_client(SETTINGS.redis_url, database=TEST_REDIS_DATABASE)
    try:
        await check_redis(created)
    except RedisUnavailableError:
        await created.aclose()
        pytest.skip(SKIP_REDIS)

    # **清空之前先确认连的是哪个库。** 这一句不是多余的谨慎：`db=` 曾被 URL 里的 `/0`
    # 静默盖掉，于是每条用例都在冲业务库，而且投出去的测试任务被真的 worker 领走 ——
    # 那是要花钱的模型调用。整件事没有一处报错，是靠一条断言里冒出真实中文回答才发现的
    connected = created.connection_pool.connection_kwargs["db"]
    if connected != TEST_REDIS_DATABASE:
        await created.aclose()
        pytest.fail(f"测试连到了 {connected} 号库而不是 {TEST_REDIS_DATABASE} 号，拒绝 flushdb")

    await created.flushdb()
    await created.connection_pool.disconnect()
    try:
        yield created
    finally:
        await created.aclose()
