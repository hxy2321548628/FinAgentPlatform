"""``langgraph dev`` 使用项目 Postgres 的检查点。"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.store.checkpoint import open_checkpoint
from config import get_settings


@asynccontextmanager
async def create_checkpointer() -> AsyncGenerator[AsyncPostgresSaver]:
    """打开项目共用的 Postgres checkpointer，并在服务器退出时关闭连接池。"""
    checkpoint = await open_checkpoint(get_settings().postgres_conninfo())
    try:
        yield checkpoint.saver
    finally:
        await checkpoint.aclose()
