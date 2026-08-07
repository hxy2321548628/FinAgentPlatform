"""`threads` 表的读写。

**每一个公开的查询方法都要求 `user_id`，没有不带它的重载。** 这不是麻烦，是隔离本身：
多租户系统最常见的越权来源就是「某个接口忘了加 where 条件」，而只要这一层不提供
「不带 user 也能查」的入口，那种遗漏就写不出来。

**管理员不例外。** 它多的是账号与配额的管理能力，不是看别人会话的能力 ——
因此这里没有任何绕过过滤的旁路。这条边界最容易为了「方便排查问题」被悄悄破坏，
一旦破坏就很难再收回来。
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from thread.model import ThreadRecord

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Thread:
    """一个会话。"""

    id: str
    user_id: str
    title: str


class ThreadRepository:
    """`threads` 表的读写。

    Args:
        engine: 到 Postgres 的异步引擎。
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def create(self, *, user_id: str, title: str = "") -> Thread:
        """开一个新会话。

        **表先于目录**：id 由这里发，端点拿着它再去 broker 建目录。反过来的话，
        「会话存不存在」就有两个真相源，而它们会分叉。

        Args:
            user_id: 会话的主人。
            title: 会话标题，本期没有改标题的接口，建出来就是空的。

        Returns:
            建出来的会话。
        """
        now = datetime.now(UTC)
        record = ThreadRecord(id=uuid4(), user_id=UUID(user_id), title=title, created_at=now, updated_at=now)
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            session.add(record)
            await session.commit()
        return _to_thread(record)

    async def get(self, thread_id: str, *, user_id: str) -> Thread | None:
        """查一个会话，**只查得到自己的那些**。

        别人的会话与根本不存在的会话在这里是同一个结果 —— 端点因此自然落到 404，
        不需要再写一句鉴权判断。

        Args:
            thread_id: 会话标识。
            user_id: 当前用户。

        Returns:
            找到的会话；不存在、id 不合法，或不属于该用户则 None。
        """
        identifier, owner = _parse(thread_id), _parse(user_id)
        if identifier is None or owner is None:
            return None
        async with AsyncSession(self._engine) as session:
            found = await session.exec(
                select(ThreadRecord).where(
                    col(ThreadRecord.id) == identifier,
                    col(ThreadRecord.user_id) == owner,
                )
            )
            record = found.first()
        return None if record is None else _to_thread(record)

    async def delete(self, thread_id: str, *, user_id: str) -> None:
        """删掉一个会话。

        **只在建目录失败时用**：那一刻表里已经有行、目录却没建成，留着就是半个会话。
        本期没有删会话的接口，这是补偿路径而不是功能。

        Args:
            thread_id: 会话标识。
            user_id: 当前用户。
        """
        identifier, owner = _parse(thread_id), _parse(user_id)
        if identifier is None or owner is None:
            return
        async with AsyncSession(self._engine) as session:
            record = await session.get(ThreadRecord, identifier)
            if record is None or record.user_id != owner:
                return
            await session.delete(record)
            await session.commit()


def _to_thread(record: ThreadRecord) -> Thread:
    return Thread(id=record.id.hex, user_id=record.user_id.hex, title=record.title)


def _parse(identifier: str) -> UUID | None:
    """标识来自 URL 与 session，解析不了就是「查不到」，不是 500。"""
    try:
        return UUID(identifier)
    except ValueError:
        return None
