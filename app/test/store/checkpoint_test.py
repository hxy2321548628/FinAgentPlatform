"""会话 checkpoint 落库的测试。

**核心断言是「换一个 saver 实例还读得到」** —— 那正是进程重启后追问能不能接上上文。
P0 用 `InMemorySaver` 时同进程内也能追问，但没人验过跨重启，这条是本期第一次覆盖。

用真 Postgres 而不是替身：要验的就是数据落没落到库里。
"""

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import CheckpointMetadata, empty_checkpoint
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from store.checkpoint import Checkpoint, open_checkpoint
from test.conftest import TEST_POSTGRES_CONNINFO

# 框架自己建的表。手工改过就等着下次升级 LangGraph 时冲突，因此它们不进 Alembic
FRAMEWORK_TABLE = ("checkpoints", "checkpoint_writes", "checkpoint_blobs", "checkpoint_migrations")


def _config(thread_id: str) -> RunnableConfig:
    return {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}


@pytest.fixture
async def checkpoint(live_engine: AsyncEngine) -> AsyncIterator[Checkpoint]:
    """真的 checkpointer。`live_engine` 只用来决定「Postgres 在不在」。"""
    opened = await open_checkpoint(TEST_POSTGRES_CONNINFO)
    try:
        yield opened
    finally:
        await opened.aclose()


async def test_setup_creates_the_framework_tables(checkpoint: Checkpoint, live_engine: AsyncEngine) -> None:
    async with live_engine.connect() as connection:
        result = await connection.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"),
        )
        existing = {row[0] for row in result}

    assert set(FRAMEWORK_TABLE) <= existing


async def test_a_thread_written_by_one_saver_is_read_by_the_next(checkpoint: Checkpoint) -> None:
    """换一个 saver 实例就是换一个进程 —— 会话历史必须还在。"""
    thread_id = uuid4().hex
    await checkpoint.saver.aput(_config(thread_id), empty_checkpoint(), CheckpointMetadata(), {})

    reopened = await open_checkpoint(TEST_POSTGRES_CONNINFO)
    try:
        restored = await reopened.saver.aget_tuple(_config(thread_id))
    finally:
        await reopened.aclose()

    assert restored is not None
    assert restored.config["configurable"]["thread_id"] == thread_id


async def test_threads_do_not_leak_into_each_other(checkpoint: Checkpoint) -> None:
    """会话隔离靠 thread_id。串了的话，一位教师会看到另一位的历史。"""
    written = uuid4().hex
    await checkpoint.saver.aput(_config(written), empty_checkpoint(), CheckpointMetadata(), {})

    assert await checkpoint.saver.aget_tuple(_config(uuid4().hex)) is None


async def test_setup_is_idempotent(checkpoint: Checkpoint) -> None:
    """每次进程启动都会跑一次 setup，跑第二次不能炸。"""
    await checkpoint.saver.setup()

    thread_id = uuid4().hex
    await checkpoint.saver.aput(_config(thread_id), empty_checkpoint(), CheckpointMetadata(), {})
    assert await checkpoint.saver.aget_tuple(_config(thread_id)) is not None
