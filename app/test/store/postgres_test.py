"""Postgres 接入的测试。

核心断言只有一条：**连不上时 `check` 要抛，不能悄悄放行**。步骤零的验证标准②
就是它 —— 放行的话，故障会推迟到第一次落库才暴露。
"""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from store.postgres import PostgresUnavailableError, build_dsn, check, create_engine

# 一个不会有人监听的端口。连不上是立刻的 ECONNREFUSED，不是超时
DEAD_DSN = "postgresql+psycopg://zuel:zuel@127.0.0.1:1/zuel"


async def test_check_raises_when_postgres_is_unreachable() -> None:
    dead = create_engine(DEAD_DSN, pool_size=1)
    try:
        with pytest.raises(PostgresUnavailableError):
            await check(dead)
    finally:
        await dead.dispose()


def test_a_password_with_url_punctuation_survives_the_dsn() -> None:
    """口令里出现 @ 或 / 时不转义的话，连的就是另一个主机上的另一个库。"""
    dsn = build_dsn(host="db", port=5432, user="zuel", password="p@ss/w:rd", database="zuel")

    assert dsn == "postgresql+psycopg://zuel:p%40ss%2Fw%3Ard@db:5432/zuel"


async def test_check_passes_against_a_live_postgres(live_engine: AsyncEngine) -> None:
    await check(live_engine)


async def test_a_live_engine_can_run_a_query(live_engine: AsyncEngine) -> None:
    """体检通过之后引擎要真的能用，而不只是握手成功。"""
    async with live_engine.connect() as connection:
        result = await connection.execute(text("SELECT 42"))
        assert result.scalar_one() == 42
