"""到 Postgres 的连接池，以及启动时的一次体检。

**体检不是多余的一次查询**：连不上时进程要在启动那一刻失败，而不是撑到第一次落库才炸。
一个「能启动但一查就 500」的进程，会让之后每一次故障都多一个候选原因。

驱动统一用 psycopg3。DSN 里的 `+psycopg` 只是告诉 SQLAlchemy 走哪个驱动，
而 LangGraph 的 checkpointer 直接吃 psycopg —— 两边因此共用一个驱动，
不必为一张表再拖进第二个。
"""

import logging
from urllib.parse import quote

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

logger = logging.getLogger(__name__)

# SQLAlchemy 靠这个后缀选驱动；LangGraph 的 checkpointer 用的是原生 psycopg，它不认。
# 两种形状由同一个函数拼，才不会出现「引擎连 A 库、checkpointer 连 B 库」
DRIVER = "postgresql+psycopg"
NATIVE_DRIVER = "postgresql"

# 开发机与 CI 的默认库。compose 的 postgres 服务与 CI workflow 的 services
# 都按这一组值起，因此本机跑门禁不必额外配任何东西。
#
# **端口是 5433 不是 5432**：装了系统 Postgres 的机器上 5432 已被占用，而「连错了库」
# 这种故障不报错 —— 平台自己的 Postgres 在任何宿主机上都映射到 5433，
# 默认值因此永远指向对的那一个。容器网络内部仍是 5432，由 compose 覆盖
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5433
DEFAULT_USER = "zuel"
DEFAULT_PASSWORD = "zuel"
DEFAULT_DATABASE = "zuel"

# SQLAlchemy 这一侧的连接数。它只服务 run 元数据的读写（每个 run 几次），
# 与 checkpointer 那条独立的 psycopg 池子互不相干
DEFAULT_POOL_SIZE = 5


class PostgresUnavailableError(RuntimeError):
    """连不上 Postgres。

    抛在启动路径上，让进程直接起不来。
    """


def build_dsn(*, host: str, port: int, user: str, password: str, database: str, driver: str = DRIVER) -> str:
    """把连接参数拼成 DSN。

    **配置拆成五项而不是一整条连接串**：compose 部署与本机直接跑 uvicorn 只差一个主机名，
    拆开之后 compose 里只需覆盖 `POSTGRES_HOST` 这一个字面量 —— 整条 DSN 带着密码，
    那就得走 compose 的变量插值，而插值只认 shell 里 export 过的值，等于把口令搬进 shell 历史。

    Args:
        host: 主机名或 IP。
        port: 端口。
        user: 用户名。
        password: 口令，其中的 `@` `/` `:` 等字符会被转义。
        database: 库名。
        driver: 协议前缀。默认给 SQLAlchemy 用，checkpointer 那边传 `NATIVE_DRIVER`。

    Returns:
        形如 `postgresql+psycopg://user:password@host:5432/db`。
    """
    credential = f"{quote(user, safe='')}:{quote(password, safe='')}"
    return f"{driver}://{credential}@{host}:{port}/{database}"


# 开发机与 CI 的默认连接串，测试连不上时会据此 skip
DEFAULT_DSN = build_dsn(
    host=DEFAULT_HOST,
    port=DEFAULT_PORT,
    user=DEFAULT_USER,
    password=DEFAULT_PASSWORD,
    database=DEFAULT_DATABASE,
)


def create_engine(dsn: str, *, pool_size: int = DEFAULT_POOL_SIZE) -> AsyncEngine:
    """按 DSN 建一个异步引擎。

    **建引擎不会连接**，真正的连接发生在第一次用它的时候 —— 因此建完必须紧跟一次
    `check`，否则「连不上」这件事会拖到第一个请求才暴露。

    Args:
        dsn: 形如 `postgresql+psycopg://user:password@host:5432/db`。
        pool_size: 常驻连接数。

    Returns:
        可直接开会话的引擎。
    """
    return create_async_engine(dsn, pool_size=pool_size, pool_pre_ping=True)


async def check(engine: AsyncEngine) -> None:
    """确认连得上，连不上就抛。

    Args:
        engine: 待体检的引擎。

    Raises:
        PostgresUnavailableError: 连接不上或查询失败。
    """
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        message = f"连不上 Postgres：{exc}"
        raise PostgresUnavailableError(message) from exc
