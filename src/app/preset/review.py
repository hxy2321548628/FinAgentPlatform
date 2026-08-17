"""Agent 与 Skill 共用的版本审核记录读写。"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Select, update
from sqlalchemy import select as sa_select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.preset.model import (
    REVIEWABLE_KIND,
    AgentRecord,
    AgentVersionRecord,
    ResourceKind,
    ReviewRecord,
    ReviewStatus,
)
from app.preset.skill import SkillRecord, SkillVersionRecord
from app.user.model import UserRecord

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Review:
    """一条审核记录。"""

    id: str
    target_kind: ResourceKind
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
    """审核队列的一行；两类资源只填各自适用的内容字段。"""

    review: Review
    owner_name: str
    description: str
    subject: str
    version: int
    agent_id: str | None = None
    agent_name: str | None = None
    system_prompt: str | None = None
    skill_id: str | None = None
    skill_name: str | None = None
    file_count: int | None = None
    total_bytes: int | None = None


class ReviewRepository:
    """`reviews` 表的读写与两类资源的审核队列。"""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def submit(
        self,
        *,
        target_id: str,
        submitted_by: str,
        responsibility_confirmed: bool,
        target_kind: ResourceKind = ResourceKind.AGENT,
    ) -> Review | None:
        """提审一个版本；同类同版本已有待审记录时返回 None。"""
        version = _parse(target_id)
        submitter = _parse(submitted_by)
        if version is None or submitter is None:
            return None
        record = ReviewRecord(
            id=uuid4(),
            target_kind=target_kind,
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
        logger.info("提审：target_kind=%s target_id=%s by=%s", target_kind.value, target_id, submitted_by)
        return _to_review(record)

    async def get(self, review_id: str) -> Review | None:
        """按标识读取一条审核记录。"""
        identifier = _parse(review_id)
        if identifier is None:
            return None
        async with AsyncSession(self._engine) as session:
            record = await session.get(ReviewRecord, identifier)
        return None if record is None else _to_review(record)

    async def decide(self, review_id: str, *, reviewer_id: str, approved: bool, reason: str | None) -> bool:
        """条件更新一条待审记录，避免两个审核员互相覆盖。"""
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
                reason=reason,
                reviewed_by=reviewer,
                decided_at=datetime.now(UTC),
            )
            .returning(col(ReviewRecord.id))
        )
        async with self._engine.begin() as connection:
            changed = (await connection.execute(statement)).first()
        return changed is not None

    async def get_item(self, review_id: str) -> ReviewItem | None:
        """按审核标识回读带资源详情的一行。"""
        review = await self.get(review_id)
        if review is None:
            return None
        statement = _item_select(review.target_kind).where(col(ReviewRecord.id) == UUID(review.id))
        items = await self._items(statement, review.target_kind)
        return None if not items else items[0]

    async def list_pending(self) -> list[ReviewItem]:
        """全部待审，跨资源按提交时间升序。"""
        items = await self._for_status(ReviewStatus.PENDING)
        return sorted(items, key=lambda one: one.review.created_at)

    async def list_decided(self, *, limit: int) -> list[ReviewItem]:
        """最近处理过的记录，跨资源按决策时间倒序。"""
        if limit <= 0:
            return []
        items: list[ReviewItem] = []
        for kind in REVIEWABLE_KIND:
            statement = (
                _item_select(kind)
                .where(col(ReviewRecord.status) != ReviewStatus.PENDING)
                .order_by(col(ReviewRecord.decided_at).desc())
                .limit(limit)
            )
            items.extend(await self._items(statement, kind))
        return sorted(
            items,
            key=lambda one: one.review.decided_at or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )[:limit]

    async def list_for_target(
        self,
        target_ids: Sequence[str],
        *,
        target_kind: ResourceKind = ResourceKind.AGENT,
    ) -> list[Review]:
        """一批同类版本上的审核记录，最近的排前。"""
        wanted = [parsed for parsed in (_parse(one) for one in target_ids) if parsed is not None]
        if not wanted:
            return []
        async with AsyncSession(self._engine) as session:
            found = await session.exec(
                select(ReviewRecord)
                .where(
                    col(ReviewRecord.target_kind) == target_kind,
                    col(ReviewRecord.target_id).in_(wanted),
                )
                .order_by(col(ReviewRecord.created_at).desc())
            )
            return [_to_review(one) for one in found.all()]

    async def _for_status(self, status: ReviewStatus) -> list[ReviewItem]:
        items: list[ReviewItem] = []
        for kind in REVIEWABLE_KIND:
            statement = _item_select(kind).where(col(ReviewRecord.status) == status)
            items.extend(await self._items(statement, kind))
        return items

    async def _items(self, statement: Select[tuple[object, ...]], kind: ResourceKind) -> list[ReviewItem]:
        async with self._engine.connect() as connection:
            rows = (await connection.execute(statement)).mappings().all()
        return [_to_item(row, kind) for row in rows]


def _item_select(kind: ResourceKind) -> Select[tuple[object, ...]]:
    """按资源种类拼一条带内容详情的查询。

    **三种 kind 各自显式分支，没有兜底的 `else`。** 原来是「AGENT 走一支、其余都走
    skill 那一支」，加进 `ResourceKind.MCP` 之后它会把 skill 的待审记录查两遍、
    第二遍还标成 MCP —— 审核队列里每条 skill 申请出现两次，而这个错不报任何异常。

    Raises:
        ValueError: MCP 的审核不走 reviewer 队列，它也没有版本行可 join。
    """
    common: tuple[ColumnElement[object], ...] = (
        col(ReviewRecord.id).label("id"),
        col(ReviewRecord.target_id).label("target_id"),
        col(ReviewRecord.status).label("status"),
        col(ReviewRecord.responsibility_confirmed).label("responsibility_confirmed"),
        col(ReviewRecord.reason).label("reason"),
        col(ReviewRecord.submitted_by).label("submitted_by"),
        col(ReviewRecord.reviewed_by).label("reviewed_by"),
        col(ReviewRecord.created_at).label("created_at"),
        col(ReviewRecord.decided_at).label("decided_at"),
    )
    if kind is ResourceKind.AGENT:
        return (
            sa_select(
                *common,
                col(AgentRecord.id).label("resource_id"),
                col(AgentRecord.name).label("resource_name"),
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
    if kind is ResourceKind.MCP:
        raise ValueError("MCP 的审核由管理员在 MCP 后台处理，不进 reviewer 队列")
    return (
        sa_select(
            *common,
            col(SkillRecord.id).label("resource_id"),
            col(SkillRecord.name).label("resource_name"),
            col(UserRecord.name).label("owner_name"),
            col(SkillVersionRecord.description).label("description"),
            col(SkillRecord.subject).label("subject"),
            col(SkillVersionRecord.version).label("version"),
            col(SkillVersionRecord.file_count).label("file_count"),
            col(SkillVersionRecord.total_bytes).label("total_bytes"),
        )
        .join(SkillVersionRecord, onclause=col(SkillVersionRecord.id) == col(ReviewRecord.target_id))
        .join(SkillRecord, onclause=col(SkillRecord.id) == col(SkillVersionRecord.skill_id))
        .join(UserRecord, onclause=col(UserRecord.id) == col(SkillRecord.owner_id))
        .where(col(ReviewRecord.target_kind) == ResourceKind.SKILL)
    )


def _to_item(row: object, kind: ResourceKind) -> ReviewItem:
    values = row
    review = Review(
        id=values["id"].hex,  # type: ignore[index]
        target_kind=kind,
        target_id=values["target_id"].hex,  # type: ignore[index]
        status=ReviewStatus(values["status"]),  # type: ignore[index]
        responsibility_confirmed=values["responsibility_confirmed"],  # type: ignore[index]
        reason=values["reason"],  # type: ignore[index]
        submitted_by=values["submitted_by"].hex,  # type: ignore[index]
        reviewed_by=None if values["reviewed_by"] is None else values["reviewed_by"].hex,  # type: ignore[index]
        created_at=values["created_at"],  # type: ignore[index]
        decided_at=values["decided_at"],  # type: ignore[index]
    )
    common = {
        "review": review,
        "owner_name": values["owner_name"],  # type: ignore[index]
        "description": values["description"],  # type: ignore[index]
        "subject": values["subject"],  # type: ignore[index]
        "version": values["version"],  # type: ignore[index]
    }
    if kind is ResourceKind.AGENT:
        return ReviewItem(
            **common,
            agent_id=values["resource_id"].hex,  # type: ignore[index]
            agent_name=values["resource_name"],  # type: ignore[index]
            system_prompt=values["system_prompt"],  # type: ignore[index]
        )
    if kind is ResourceKind.MCP:
        raise ValueError("MCP 的审核由管理员在 MCP 后台处理，不进 reviewer 队列")
    return ReviewItem(
        **common,
        skill_id=values["resource_id"].hex,  # type: ignore[index]
        skill_name=values["resource_name"],  # type: ignore[index]
        file_count=values["file_count"],  # type: ignore[index]
        total_bytes=values["total_bytes"],  # type: ignore[index]
    )


def _to_review(record: ReviewRecord) -> Review:
    return Review(
        id=record.id.hex,
        target_kind=record.target_kind,
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
    try:
        return UUID(identifier)
    except ValueError:
        return None
