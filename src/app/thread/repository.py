"""`threads` 表的读写。

**每一个公开的查询方法都要求 `user_id`，没有不带它的重载。** 这不是麻烦，是隔离本身：
多租户系统最常见的越权来源就是「某个接口忘了加 where 条件」，而只要这一层不提供
「不带 user 也能查」的入口，那种遗漏就写不出来。

**管理员不例外。** 它多的是账号与配额的管理能力，不是看别人会话的能力 ——
因此这里没有任何绕过过滤的旁路。这条边界最容易为了「方便排查问题」被悄悄破坏，
一旦破坏就很难再收回来。

**删会话是软删除，唯一的例外是 `purge`。** 理由与外键有关，写在 `delete` 上。
因此每一条查询除了 `user_id` 还要带上「没被删」这个条件 —— 两个过滤条件集中在
`_visible` 一处，各写各的迟早会漏掉一处，而漏掉的症状是「删了还在」。
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import and_
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import col, select, tuple_
from sqlmodel.ext.asyncio.session import AsyncSession

from app.thread.model import ThreadRecord
from cursor import DEFAULT_PAGE_SIZE, Page, decode, encode, split

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Thread:
    """一个会话。"""

    id: str
    user_id: str
    title: str
    agent_config: dict[str, object]
    created_at: datetime
    # 最后一次活动。**列表按它排序而不是按建立时间** —— 否则老会话再问一句也沉在底下
    updated_at: datetime


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
            title: 会话标题。建出来是空的，由首次提问后的一次轻量模型调用填上。

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
        """查一个会话，**只查得到自己那些还没删的**。

        别人的会话、已经删掉的会话与根本不存在的会话在这里是同一个结果 ——
        端点因此自然落到 404，不需要再写一句鉴权判断。

        Args:
            thread_id: 会话标识。
            user_id: 当前用户。

        Returns:
            找到的会话；不存在、id 不合法、已删除，或不属于该用户则 None。
        """
        record = await self._find(thread_id, user_id=user_id)
        return None if record is None else _to_thread(record)

    async def list(
        self,
        *,
        user_id: str,
        cursor: str | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
        query: str | None = None,
    ) -> Page[Thread]:
        """列出这个用户的会话，最近活动的在前。

        Args:
            user_id: 当前用户。
            cursor: 上一页给的游标，不传则从头。
            limit: 一页几条。
            query: 按标题模糊搜索（大小写不敏感），不传则全部。

        Returns:
            这一页会话，以及取下一页要带的游标。

        Raises:
            CursorError: 游标不合法。
        """
        owner = _parse(user_id)
        if owner is None:
            return Page(items=[], next_cursor=None)

        statement = select(ThreadRecord).where(_visible(owner))
        if query:
            # ilike 自带参数绑定，无注入面；%/_ 按通配符语义处理是搜索的预期行为
            statement = statement.where(col(ThreadRecord.title).ilike(f"%{query}%"))
        if cursor is not None:
            # 行值比较而不是 `updated_at < x OR (updated_at = x AND id < y)`：
            # 后者要把同一组值写两遍，而改排序时漏改一处不会报错，只会让翻页少几条
            statement = statement.where(tuple_(col(ThreadRecord.updated_at), col(ThreadRecord.id)) < decode(cursor))

        async with AsyncSession(self._engine) as session:
            found = await session.exec(
                statement.order_by(col(ThreadRecord.updated_at).desc(), col(ThreadRecord.id).desc()).limit(limit + 1)
            )
            page, has_more = split(list(found.all()), limit)

        return Page(
            items=[_to_thread(one) for one in page],
            next_cursor=encode(page[-1].updated_at, page[-1].id) if has_more else None,
        )

    async def update(
        self,
        thread_id: str,
        *,
        user_id: str,
        title: str | None = None,
        agent_config: dict[str, object] | None = None,
    ) -> Thread | None:
        """改一个会话的标题或配置。

        **两个字段各自可选**：只传标题时配置原样留着 —— 一次改名把 agent 配置清空，
        是那种改完当时没事、下次跑分析才发现的故障。

        Args:
            thread_id: 会话标识。
            user_id: 当前用户。
            title: 新标题，不传则不动。
            agent_config: 新配置，整块替换，不传则不动。

        Returns:
            改完的会话；查不到（不存在、已删除或不属于该用户）则 None。
        """
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            record = await self._find(thread_id, user_id=user_id, session=session)
            if record is None:
                return None
            if title is not None:
                record.title = title
            if agent_config is not None:
                record.agent_config = agent_config
            # 改标题也是一次活动。不动这一列的话，刚改过名的会话仍旧沉在列表底下
            record.updated_at = datetime.now(UTC)
            session.add(record)
            await session.commit()
        return _to_thread(record)

    async def touch(self, thread_id: str, *, user_id: str) -> None:
        """把会话的最后活动时间推到此刻。

        提交分析时调一次 —— 会话列表按活跃度排序，靠的就是这一下。

        Args:
            thread_id: 会话标识。
            user_id: 当前用户。
        """
        await self.update(thread_id, user_id=user_id)

    async def delete(self, thread_id: str, *, user_id: str) -> bool:
        """删掉一个会话。**只打删除标记，行留着。**

        硬删会撞上 `runs.thread_id` 的外键，而顺着删掉 runs 等于把成本账本挖掉一块 ——
        `runs` 是数据设计里明确「不清」的那张表，它是历史的索引。教师删会话要的是
        「从我的列表里消失、别再占磁盘」：前者由这个标记负责，后者由端点接着让 broker
        真删 workspace 目录负责。

        Args:
            thread_id: 会话标识。
            user_id: 当前用户。

        Returns:
            这一次调用是否真的删掉了什么。已经删过的返回 False —— 那是幂等，不是错误。
        """
        async with AsyncSession(self._engine) as session:
            record = await self._find(thread_id, user_id=user_id, session=session)
            if record is None:
                return False
            record.deleted_at = datetime.now(UTC)
            session.add(record)
            await session.commit()
        return True

    async def purge(self, thread_id: str, *, user_id: str) -> None:
        """把一行真的删掉。

        **只在建目录失败时用**：那一刻表里已经有行、目录却没建成，留着就是半个会话。
        这是补偿路径而不是功能 —— 那一行刚建出来，还没有任何 run 指着它，
        因此不受 `delete` 那条外键顾虑的约束。

        Args:
            thread_id: 会话标识。
            user_id: 当前用户。
        """
        async with AsyncSession(self._engine) as session:
            record = await self._find(thread_id, user_id=user_id, session=session)
            if record is None:
                return
            await session.delete(record)
            await session.commit()

    async def _find(self, thread_id: str, *, user_id: str, session: AsyncSession | None = None) -> ThreadRecord | None:
        """按 id 取一行，套上「是我的、且没删」这两个过滤条件。

        Args:
            thread_id: 会话标识。
            user_id: 当前用户。
            session: 复用调用方的会话，改写那几个方法需要它 —— 各开各的会话的话，
                读到的对象不归调用方的会话管，改了也提交不出去。

        Returns:
            找到的行，否则 None。
        """
        identifier, owner = _parse(thread_id), _parse(user_id)
        if identifier is None or owner is None:
            return None
        statement = select(ThreadRecord).where(col(ThreadRecord.id) == identifier, _visible(owner))
        if session is not None:
            return (await session.exec(statement)).first()
        async with AsyncSession(self._engine) as opened:
            return (await opened.exec(statement)).first()


def _visible(owner: UUID) -> ColumnElement[bool]:
    """一个用户看得见的那些会话：他自己的，且没被删的。"""
    return and_(col(ThreadRecord.user_id) == owner, col(ThreadRecord.deleted_at).is_(None))


def _to_thread(record: ThreadRecord) -> Thread:
    return Thread(
        id=record.id.hex,
        user_id=record.user_id.hex,
        title=record.title,
        agent_config=record.agent_config,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _parse(identifier: str) -> UUID | None:
    """标识来自 URL 与 session，解析不了就是「查不到」，不是 500。"""
    try:
        return UUID(identifier)
    except ValueError:
        return None
