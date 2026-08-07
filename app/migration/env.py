"""Alembic 的运行时装配。

连接串取自 `StoreSettings`，**不写在 alembic.ini 里** —— 那份配置里有口令，
且 compose 与本机跑的主机名不同。分出 `StoreSettings` 这一层，就是为了让迁移
不必凑齐 `DEEPSEEK_API_KEY` 之类跟建表无关的东西。

只跑 online 模式：离线模式产出的是 SQL 文本，本项目没有「把 SQL 交给 DBA 执行」
这个环节，留着只会多一条没人走的路径。
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlmodel import SQLModel

from config import StoreSettings

# 导入是为了让表定义注册进 SQLModel.metadata，autogenerate 才看得见它们
import run.repository  # noqa: F401  isort:skip

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

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
