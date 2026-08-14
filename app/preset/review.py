"""审核记录的读写：提审、决策、待审队列。

**审的是版本，不是 agent。** 盯着 agent 审的话，审过一次之后作者随便改内容都进得了
广场 —— 那等于没有审核。因此 `target_id` 指的是 `agent_versions` 的行，改一版要重审
一版；没审的那一版进不了广场，而组内照常看得见已发布的最新版。

**审核管的是「别人能不能看见」，不是「作者能不能用」。** 被拒的版本作者与组员照常
可用，只是广场进不去。这条精神落在查询上就是：这一层从不参与 `list_available`，
只参与 `list_catalog`。

**拒绝理由后端也校验。** 只靠前端拦的话，任何一次直接打接口都能留下一条没有理由的
拒绝，而作者看到的是「被拒了，没说为什么」。
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Select, update
from sqlalchemy import select as sa_select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from preset.model import (
    AgentRecord,
    AgentVersionRecord,
    ResourceKind,
    ReviewRecord,
    ReviewStatus,
)
from user.model import UserRecord

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Review:
    """一条审核记录。"""

    id: str
    target_id: str
    status: ReviewStatus
    responsibility_confirmed: bool
    reason: str | None
    submitted_by: str
    reviewed_by: str | None
    created_at: datetime
    decided_at: datetime | None


@dataclass(frozen=True)
class ReviewItem:
    """待审队列里的一条：审核记录，连同 reviewer 判断时需要看的全部东西。

    **提示词全文在里面。** reviewer 要审的正是这段文字，让他再点一次去别处取
    等于把审核变成走过场。
    """

    review: Review
    agent_id: str
    agent_name: str
    owner_name: str
    description: str
    subject: str
    version: int
    system_prompt: str


class ReviewRepository:
    """`reviews` 表的读写。

    Args:
        engine: 到 Postgres 的异步引擎。
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def submit(self, *, target_id: str, submitted_by: str, responsibility_confirmed: bool) -> Review | None:
        """提审一个版本。

        Args:
            target_id: 要提审的版本行标识。调用方应先确认它已发布且归当前用户。
            submitted_by: 提审的人。
            responsibility_confirmed: 责任确认勾了没有。调用方负责在没勾时直接拒绝，
                这里只如实记下 —— 出了事要拿这一列说话。

        Returns:
            新建的审核记录；**这一版已经挂着一条待审时返回 None** ——
            那是部分唯一索引挡下的，连点两次只该留下一条待办。
        """
        version = _parse(target_id)
        submitter = _parse(submitted_by)
        if version is None or submitter is None:
            return None
        record = ReviewRecord(
            id=uuid4(),
            target_kind=ResourceKind.AGENT,
            target_id=version,
            status=ReviewStatus.PENDING,
            responsibility_confirmed=responsibility_confirmed,
            submitted_by=submitter,
            created_at=datetime.now(UTC),
        )
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            session.add(record)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                return None
        logger.info("提审：target_id=%s by=%s", target_id, submitted_by)
        return _to_review(record)

    async def get(self, review_id: str) -> Review | None:
        """按 id 查一条审核记录。

        Args:
            review_id: 审核标识。

        Returns:
            找到的记录，否则 None。
        """
        identifier = _parse(review_id)
        if identifier is None:
            return None
        async with AsyncSession(self._engine) as session:
            record = await session.get(ReviewRecord, identifier)
        return None if record is None else _to_review(record)

    async def decide(self, review_id: str, *, reviewer_id: str, approved: bool, reason: str | None) -> bool:
        """通过或拒绝一条待审。

        **状态是条件更新而不是「先读再写」**：两个 reviewer 各点一次时，
        先读再写的那一份会让第二次把拒绝改成通过。

        Args:
            review_id: 审核标识。
            reviewer_id: 决策的人。
            approved: 通过还是拒绝。
            reason: 拒绝理由。调用方负责在拒绝时确认它非空。

        Returns:
            这一次是否真的改动了。已经决策过的返回 False。
        """
        identifier, reviewer = _parse(review_id), _parse(reviewer_id)
        if identifier is None or reviewer is None:
            return False
        statement = (
            update(ReviewRecord)
            .where(
                col(ReviewRecord.id) == identifier,
                col(ReviewRecord.status) == ReviewStatus.PENDING,
            )
            .values(
                status=ReviewStatus.APPROVED if approved else ReviewStatus.REJECTED,
                reviewed_by=reviewer,
                reason=reason,
                decided_at=datetime.now(UTC),
            )
            .returning(col(ReviewRecord.id))
        )
        async with self._engine.begin() as connection:
            decided = (await connection.execute(statement)).first()
        if decided is None:
            return False
        logger.info("审核决策：review_id=%s approved=%s by=%s", review_id, approved, reviewer_id)
        return True

    async def get_item(self, review_id: str) -> ReviewItem | None:
        """按 id 查一条审核记录，连同它指向的 agent 与版本。

        Args:
            review_id: 审核标识。

        Returns:
            找到的队列行，否则 None。
        """
        identifier = _parse(review_id)
        if identifier is None:
            return None
        found = await self._item(_item_select().where(col(ReviewRecord.id) == identifier))
        return found[0] if found else None

    async def list_pending(self) -> list[ReviewItem]:
        """全部待审，**先提交的排前面**。

        没有分页 —— 学院内部平台上待审队列是个位数量级，分页只会多一份要维护的游标。

        Returns:
            待审的每一条一行，带着 reviewer 判断需要的全部信息。
        """
        statement = _item_select().where(col(ReviewRecord.status) == ReviewStatus.PENDING)
        return await self._item(statement.order_by(col(ReviewRecord.created_at)))

    async def list_decided(self, *, limit: int) -> list[ReviewItem]:
        """最近处理过的那些，最新的排前面。

        队列清空之后 reviewer 打开这一页看到的不该是一片空白 —— 「我刚才审的那条呢」
        是必然会问的一句。

        Args:
            limit: 最多回几条。

        Returns:
            已决策的每一条一行。
        """
        statement = (
            _item_select()
            .where(col(ReviewRecord.status) != ReviewStatus.PENDING)
            .order_by(col(ReviewRecord.decided_at).desc())
            .limit(limit)
        )
        return await self._item(statement)

    async def list_for_target(self, target_ids: Sequence[str]) -> list[Review]:
        """一批版本上挂着的全部审核记录，**最近的排前面**。

        一次问一批而不是逐个问：作者的「我的智能体」一页上有几十个 agent、
        上百个版本，逐个查就是上百次往返。

        Args:
            target_ids: 版本行标识。

        Returns:
            这些版本上的审核记录；一条都没有则空列表。
        """
        wanted = [parsed for parsed in (_parse(one) for one in target_ids) if parsed is not None]
        if not wanted:
            return []
        async with AsyncSession(self._engine) as session:
            found = await session.exec(
                select(ReviewRecord)
                .where(
                    col(ReviewRecord.target_kind) == ResourceKind.AGENT,
                    col(ReviewRecord.target_id).in_(wanted),
                )
                .order_by(col(ReviewRecord.created_at).desc())
            )
            return [_to_review(one) for one in found.all()]

    async def _item(self, statement: Select[tuple[object, ...]]) -> list[ReviewItem]:
        async with self._engine.connect() as connection:
            found = (await connection.execute(statement)).mappings().all()
        return [
            ReviewItem(
                review=Review(
                    id=row["id"].hex,
                    target_id=row["target_id"].hex,
                    status=ReviewStatus(row["status"]),
                    responsibility_confirmed=row["responsibility_confirmed"],
                    reason=row["reason"],
                    submitted_by=row["submitted_by"].hex,
                    reviewed_by=None if row["reviewed_by"] is None else row["reviewed_by"].hex,
                    created_at=row["created_at"],
                    decided_at=row["decided_at"],
                ),
                agent_id=row["agent_id"].hex,
                agent_name=row["agent_name"],
                owner_name=row["owner_name"],
                description=row["description"],
                subject=row["subject"],
                version=row["version"],
                system_prompt=row["system_prompt"],
            )
            for row in found
        ]


def _item_select() -> Select[tuple[object, ...]]:
    """队列行的那些列。

    **按标签取值而不是按位置**：这条查询有十六列，位置索引会在某次插列时整体错位，
    而错位的症状是「说明栏里显示的是学科」，没有任何一处报错。
    """
    return (
        sa_select(
            col(ReviewRecord.id).label("id"),
            col(ReviewRecord.target_id).label("target_id"),
            col(ReviewRecord.status).label("status"),
            col(ReviewRecord.responsibility_confirmed).label("responsibility_confirmed"),
            col(ReviewRecord.reason).label("reason"),
            col(ReviewRecord.submitted_by).label("submitted_by"),
            col(ReviewRecord.reviewed_by).label("reviewed_by"),
            col(ReviewRecord.created_at).label("created_at"),
            col(ReviewRecord.decided_at).label("decided_at"),
            col(AgentRecord.id).label("agent_id"),
            col(AgentRecord.name).label("agent_name"),
            col(UserRecord.name).label("owner_name"),
            col(AgentRecord.description).label("description"),
            col(AgentRecord.subject).label("subject"),
            col(AgentVersionRecord.version).label("version"),
            col(AgentVersionRecord.system_prompt).label("system_prompt"),
        )
        .join(AgentVersionRecord, onclause=col(AgentVersionRecord.id) == col(ReviewRecord.target_id))
        .join(AgentRecord, onclause=col(AgentRecord.id) == col(AgentVersionRecord.agent_id))
        .join(UserRecord, onclause=col(UserRecord.id) == col(AgentRecord.owner_id))
        .where(col(ReviewRecord.target_kind) == ResourceKind.AGENT)
    )


def _to_review(record: ReviewRecord) -> Review:
    return Review(
        id=record.id.hex,
        target_id=record.target_id.hex,
        status=record.status,
        responsibility_confirmed=record.responsibility_confirmed,
        reason=record.reason,
        submitted_by=record.submitted_by.hex,
        reviewed_by=None if record.reviewed_by is None else record.reviewed_by.hex,
        created_at=record.created_at,
        decided_at=record.decided_at,
    )


def _parse(identifier: str) -> UUID | None:
    """标识来自 URL 与 session，解析不了就是「查不到」，不是 500。"""
    try:
        return UUID(identifier)
    except ValueError:
        return None
