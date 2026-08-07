"""Alembic 的运行时装配。

连接串取自 `StoreSettings`，**不写在 alembic.ini 里** —— 那份配置里有口令，
且 compose 与本机跑的主机名不同。分出 `StoreSettings` 这一层，就是为了让迁移
不必凑齐 `DEEPSEEK_API_KEY` 之类跟建表无关的东西。

只跑 online 模式：离线模式产出的是 SQL 文本，本项目没有「把 SQL 交给 DBA 执行」
这个环节，留着只会多一条没人走的路径。

**不调 `fileConfig`**（alembic 的模板默认会调）：它按 alembic.ini 重配整个 logging，
默认还会 `disable_existing_loggers`。后果有两个 —— 生产里它会把 `log.configure()`
装好的 JSON 输出顶掉，让迁移那几行变成夹在 JSON 中间的纯文本；测试里它会把 pytest
的日志捕获handler 一并摘掉，于是「某某情况要记一条告警」那类断言全部失效，
而失效的方式是静默的。日志配置本项目只有一处，就是 `log.configure()`。
"""

import asyncio

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlmodel import SQLModel

from config import StoreSettings

# 导入是为了让表定义注册进 SQLModel.metadata，autogenerate 才看得见它们
import run.repository  # noqa: F401  isort:skip
import thread.model  # noqa: F401  isort:skip
import user.model  # noqa: F401  isort:skip

config = context.config

# 连接串可以由调用方先设好 —— 测试据此把库指到独立的测试库上。
# 没设才回落到配置，那是命令行 `alembic upgrade head` 走的路
if not config.get_main_option("sqlalchemy.url", None):
    config.set_main_option("sqlalchemy.url", StoreSettings().postgres_dsn())

target_metadata = SQLModel.metadata


def do_run_migrations(connection: Connection) -> None:
    """在给定连接上跑迁移。"""
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """建引擎、开连接、跑迁移。"""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


asyncio.run(run_async_migrations())
