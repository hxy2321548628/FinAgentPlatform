"""Skill 目录的读写：身份、版本、共享与三条可见性查询。"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import Index, Select, Subquery, case, delete, exists, func, insert, literal, text, update
from sqlalchemy import select as sa_select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import Field, SQLModel, col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.group.model import GroupMemberRecord
from app.preset.model import (
    FIRST_VERSION,
    ResourceGroupRecord,
    ResourceKind,
    ReviewRecord,
    ReviewStatus,
    VersionStatus,
    Visibility,
    _value_enum,
)
from app.user.model import UserRecord

TABLE_NAME = "skills"
VERSION_TABLE_NAME = "skill_versions"

SKILL_NAME_INDEX = "ux_skills_owner_name"
SKILL_OWNER_INDEX = "ix_skills_owner"
VERSION_NUMBER_INDEX = "ux_skill_versions_number"
DRAFT_VERSION_INDEX = "ux_skill_versions_draft"

SKILL_NAME_CONDITION = "is_deleted = false"
DRAFT_VERSION_CONDITION = "status = 'draft'"

logger = logging.getLogger(__name__)

VersionRow = tuple[UUID, UUID, int, str, int, int, datetime | None]


class SkillRecord(SQLModel, table=True):
    """`skills` 表的一行：一个 Skill 的稳定身份。"""

    __tablename__ = TABLE_NAME
    __table_args__ = (
        Index(SKILL_OWNER_INDEX, "owner_id"),
        Index(
            SKILL_NAME_INDEX,
            "owner_id",
            "name",
            unique=True,
            postgresql_where=text(SKILL_NAME_CONDITION),
        ),
    )

    id: UUID = Field(primary_key=True)
    owner_id: UUID = Field(index=False, foreign_key="users.id")
    name: str
    subject: str = Field(default="")
    visibility: Visibility = Field(sa_column=_value_enum(Visibility))
    call_count: int = Field(default=0)
    is_deleted: bool = Field(default=False)
    created_at: datetime
    updated_at: datetime


class SkillVersionRecord(SQLModel, table=True):
    """`skill_versions` 表的一行；已发布版本不可变，草稿可被下一次上传覆盖。"""

    __tablename__ = VERSION_TABLE_NAME
    __table_args__ = (
        Index(VERSION_NUMBER_INDEX, "skill_id", "version", unique=True),
        Index(
            DRAFT_VERSION_INDEX,
            "skill_id",
            unique=True,
            postgresql_where=text(DRAFT_VERSION_CONDITION),
        ),
    )

    id: UUID = Field(primary_key=True)
    skill_id: UUID = Field(index=False, foreign_key="skills.id")
    version: int
    status: VersionStatus = Field(sa_column=_value_enum(VersionStatus))
    description: str = Field(default="")
    file_count: int
    total_bytes: int
    created_at: datetime
    released_at: datetime | None = Field(default=None)


class SkillSource(StrEnum):
    """Skill 出现在可用列表里的来路。"""

    OWNED = "owned"
    GROUP = "group"
    CATALOG = "catalog"


@dataclass(frozen=True)
class Skill:
    """一个 Skill 的稳定身份。"""

    id: str
    owner_id: str
    name: str
    subject: str
    visibility: Visibility
    call_count: int
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class SkillVersion:
    """一个 Skill 版本的元信息。"""

    id: str
    version: int
    status: VersionStatus
    description: str
    file_count: int
    total_bytes: int
    created_at: datetime
    released_at: datetime | None


@dataclass(frozen=True)
class SkillDetail:
    """作者视角的 Skill：身份、版本、作者名与共享组。"""

    skill: Skill
    owner_name: str
    versions: list[SkillVersion]
    group_ids: list[str]


@dataclass(frozen=True)
class SkillListing:
    """列表里的一条 Skill，以及这一档该展示的版本。"""

    id: str
    owner_id: str
    owner_name: str
    name: str
    description: str
    subject: str
    visibility: Visibility
    call_count: int
    version: int
    file_count: int
    total_bytes: int
    source: SkillSource
    updated_at: datetime


@dataclass(frozen=True)
class ResolvedSkill:
    """提交配置时解析出的可见 Skill 版本。"""

    skill_id: str
    name: str
    version: int


class SkillRepository:
    """`skills` / `skill_versions` / 共用关联表的读写。"""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def create(
        self,
        *,
        owner_id: str,
        name: str,
        subject: str,
        description: str,
        file_count: int,
        total_bytes: int,
    ) -> Skill | None:
        """建 Skill 身份行与 v1 草稿；同作者重名时返回 None。"""
        owner = _parse(owner_id)
        if owner is None:
            return None
        now = datetime.now(UTC)
        record = SkillRecord(
            id=uuid4(),
            owner_id=owner,
            name=name,
            subject=subject,
            visibility=Visibility.PRIVATE,
            created_at=now,
            updated_at=now,
        )
        version = SkillVersionRecord(
            id=uuid4(),
            skill_id=record.id,
            version=FIRST_VERSION,
            status=VersionStatus.DRAFT,
            description=description,
            file_count=file_count,
            total_bytes=total_bytes,
            created_at=now,
        )
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            session.add(record)
            try:
                await session.flush()
                session.add(version)
                await session.commit()
            except IntegrityError:
                await session.rollback()
                return None
        logger.info("建 Skill：skill_id=%s owner_id=%s", record.id.hex, owner_id)
        return _to_skill(record)

    async def get(self, skill_id: str, *, owner_id: str) -> Skill | None:
        """按 id 读取一个属于当前作者的 Skill。"""
        identifier, owner = _parse(skill_id), _parse(owner_id)
        if identifier is None or owner is None:
            return None
        async with AsyncSession(self._engine) as session:
            record = await session.get(SkillRecord, identifier)
        if record is None or record.owner_id != owner:
            return None
        return _to_skill(record)

    async def detail(self, skill_id: str, *, owner_id: str) -> SkillDetail | None:
        """读取一个属于当前作者的 Skill 全貌。"""
        identifier, owner = _parse(skill_id), _parse(owner_id)
        if identifier is None or owner is None:
            return None
        async with AsyncSession(self._engine) as session:
            record = await session.get(SkillRecord, identifier)
            if record is None or record.owner_id != owner:
                return None
            assembled = await self._assemble(session, [record])
        return assembled[0]

    async def update_meta(self, skill_id: str, *, owner_id: str, subject: str) -> Skill | None:
        """只改学科；name 由首版 frontmatter 冻结。"""
        identifier, owner = _parse(skill_id), _parse(owner_id)
        if identifier is None or owner is None:
            return None
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            record = await session.get(SkillRecord, identifier)
            if record is None or record.owner_id != owner or record.is_deleted:
                return None
            record.subject = subject
            record.updated_at = datetime.now(UTC)
            session.add(record)
            await session.commit()
        return _to_skill(record)

    async def write_draft(
        self,
        skill_id: str,
        *,
        owner_id: str,
        description: str,
        file_count: int,
        total_bytes: int,
    ) -> SkillVersion | None:
        """覆盖当前草稿；没有草稿时追加下一个版本号。"""
        identifier, owner = _parse(skill_id), _parse(owner_id)
        if identifier is None or owner is None:
            return None
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            skill = await session.get(SkillRecord, identifier)
            if skill is None or skill.owner_id != owner or skill.is_deleted:
                return None
            found = await session.exec(
                select(SkillVersionRecord).where(
                    col(SkillVersionRecord.skill_id) == identifier,
                    col(SkillVersionRecord.status) == VersionStatus.DRAFT,
                )
            )
            draft = found.first()
            now = datetime.now(UTC)
            if draft is None:
                highest = await session.exec(
                    select(func.max(col(SkillVersionRecord.version))).where(
                        col(SkillVersionRecord.skill_id) == identifier
                    )
                )
                draft = SkillVersionRecord(
                    id=uuid4(),
                    skill_id=identifier,
                    version=(highest.one() or 0) + 1,
                    status=VersionStatus.DRAFT,
                    description=description,
                    file_count=file_count,
                    total_bytes=total_bytes,
                    created_at=now,
                )
            else:
                draft.description = description
                draft.file_count = file_count
                draft.total_bytes = total_bytes
            skill.updated_at = now
            session.add(draft)
            session.add(skill)
            await session.commit()
        return _to_version(draft)

    async def release(self, skill_id: str, *, owner_id: str) -> SkillVersion | None:
        """把当前草稿定稿；没有草稿、越权或已删时返回 None。"""
        identifier, owner = _parse(skill_id), _parse(owner_id)
        if identifier is None or owner is None:
            return None
        now = datetime.now(UTC)
        statement = (
            update(SkillVersionRecord)
            .where(
                col(SkillVersionRecord.skill_id) == identifier,
                col(SkillVersionRecord.status) == VersionStatus.DRAFT,
                exists(
                    sa_select(1)
                    .select_from(SkillRecord)
                    .where(
                        col(SkillRecord.id) == identifier,
                        col(SkillRecord.owner_id) == owner,
                        col(SkillRecord.is_deleted).is_(False),
                    )
                ),
            )
            .values(status=VersionStatus.RELEASED, released_at=now)
            .returning(
                col(SkillVersionRecord.id),
                col(SkillVersionRecord.version),
                col(SkillVersionRecord.description),
                col(SkillVersionRecord.file_count),
                col(SkillVersionRecord.total_bytes),
                col(SkillVersionRecord.created_at),
            )
        )
        async with self._engine.begin() as connection:
            released = (await connection.execute(statement)).first()
            if released is None:
                return None
            await connection.execute(
                update(SkillRecord).where(col(SkillRecord.id) == identifier).values(updated_at=now)
            )
        logger.info("发布 Skill 版本：skill_id=%s version=%s", skill_id, released[1])
        return SkillVersion(
            id=released[0].hex,
            version=released[1],
            status=VersionStatus.RELEASED,
            description=released[2],
            file_count=released[3],
            total_bytes=released[4],
            created_at=released[5],
            released_at=now,
        )

    async def latest_released(self, skill_id: str, *, owner_id: str) -> SkillVersion | None:
        """作者提审时取自己的最新已发布版本。"""
        identifier, owner = _parse(skill_id), _parse(owner_id)
        if identifier is None or owner is None:
            return None
        async with AsyncSession(self._engine) as session:
            found = await session.exec(
                select(SkillVersionRecord)
                .join(SkillRecord, onclause=col(SkillRecord.id) == col(SkillVersionRecord.skill_id))
                .where(
                    col(SkillVersionRecord.skill_id) == identifier,
                    col(SkillVersionRecord.status) == VersionStatus.RELEASED,
                    col(SkillRecord.owner_id) == owner,
                    col(SkillRecord.is_deleted).is_(False),
                )
                .order_by(col(SkillVersionRecord.version).desc())
            )
            record = found.first()
        return None if record is None else _to_version(record)

    async def set_sharing(
        self,
        skill_id: str,
        *,
        owner_id: str,
        visibility: Visibility,
        group_ids: Sequence[str],
    ) -> bool:
        """整块替换可见性与共享组；调用方先确认作者属于这些组。"""
        identifier, owner = _parse(skill_id), _parse(owner_id)
        groups = [_parse(one) for one in group_ids]
        if identifier is None or owner is None or any(one is None for one in groups):
            return False
        wanted = [one for one in groups if one is not None] if visibility is Visibility.GROUP else []
        async with self._engine.begin() as connection:
            changed = await connection.execute(
                update(SkillRecord)
                .where(
                    col(SkillRecord.id) == identifier,
                    col(SkillRecord.owner_id) == owner,
                    col(SkillRecord.is_deleted).is_(False),
                )
                .values(visibility=visibility, updated_at=datetime.now(UTC))
                .returning(col(SkillRecord.id))
            )
            if changed.first() is None:
                return False
            await connection.execute(
                delete(ResourceGroupRecord).where(
                    col(ResourceGroupRecord.resource_kind) == ResourceKind.SKILL,
                    col(ResourceGroupRecord.resource_id) == identifier,
                )
            )
            if wanted:
                await connection.execute(
                    insert(ResourceGroupRecord),
                    [
                        {"resource_kind": ResourceKind.SKILL, "resource_id": identifier, "group_id": one}
                        for one in wanted
                    ],
                )
        return True

    async def delete(self, skill_id: str, *, owner_id: str) -> bool:
        """软删；我的列表保留，其他列表与新引用立即消失。"""
        identifier, owner = _parse(skill_id), _parse(owner_id)
        if identifier is None or owner is None:
            return False
        statement = (
            update(SkillRecord)
            .where(
                col(SkillRecord.id) == identifier,
                col(SkillRecord.owner_id) == owner,
                col(SkillRecord.is_deleted).is_(False),
            )
            .values(is_deleted=True, updated_at=datetime.now(UTC))
            .returning(col(SkillRecord.id))
        )
        async with self._engine.begin() as connection:
            deleted = (await connection.execute(statement)).first()
        if deleted is None:
            return False
        logger.info("软删 Skill：skill_id=%s by=%s", skill_id, owner_id)
        return True

    async def list_catalog(self) -> list[SkillListing]:
        """平台目录：展示每个 Skill 最新审核通过的版本。"""
        approved = _latest_approved()
        statement = (
            _listing_select(
                description=approved.c.description,
                version=approved.c.version,
                file_count=approved.c.file_count,
                total_bytes=approved.c.total_bytes,
                source=literal(SkillSource.CATALOG.value),
            )
            .join(UserRecord, onclause=col(UserRecord.id) == col(SkillRecord.owner_id))
            .join(approved, onclause=approved.c.skill_id == col(SkillRecord.id))
            .where(col(SkillRecord.is_deleted).is_(False))
            .order_by(col(SkillRecord.call_count).desc(), approved.c.released_at.desc())
        )
        return await self._listing(statement)

    async def list_available(self, user_id: str) -> list[SkillListing]:
        """我能引用的：自己的、组内共享的、平台目录里的并集。"""
        user = _parse(user_id)
        if user is None:
            return []
        return await self._listing(self._available_statement(user).order_by(col(SkillRecord.name)))

    async def list_owned(self, user_id: str) -> list[SkillDetail]:
        """我的全部 Skill，含软删行，最近改动排前。"""
        owner = _parse(user_id)
        if owner is None:
            return []
        async with AsyncSession(self._engine) as session:
            found = await session.exec(
                select(SkillRecord)
                .where(col(SkillRecord.owner_id) == owner)
                .order_by(col(SkillRecord.updated_at).desc())
            )
            return await self._assemble(session, list(found.all()))

    async def resolve(self, skill_id: str, *, user_id: str) -> ResolvedSkill | None:
        """走可用列表同一条语句解析一个 Skill。"""
        identifier, user = _parse(skill_id), _parse(user_id)
        if identifier is None or user is None:
            return None
        statement = self._available_statement(user).where(col(SkillRecord.id) == identifier)
        async with self._engine.connect() as connection:
            found = (await connection.execute(statement)).mappings().first()
        if found is None:
            return None
        return ResolvedSkill(skill_id=found["id"].hex, name=found["name"], version=found["version"])

    async def count_call(self, skill_id: str) -> None:
        """原子增加一次调用计数。"""
        identifier = _parse(skill_id)
        if identifier is None:
            return
        async with self._engine.begin() as connection:
            await connection.execute(
                update(SkillRecord)
                .where(col(SkillRecord.id) == identifier)
                .values(call_count=col(SkillRecord.call_count) + 1)
            )

    async def _assemble(self, session: AsyncSession, records: list[SkillRecord]) -> list[SkillDetail]:
        if not records:
            return []
        identifiers = [one.id for one in records]
        versions = await session.exec(
            select(SkillVersionRecord)
            .where(col(SkillVersionRecord.skill_id).in_(identifiers))
            .order_by(col(SkillVersionRecord.version))
        )
        groups = await session.exec(
            select(ResourceGroupRecord).where(
                col(ResourceGroupRecord.resource_kind) == ResourceKind.SKILL,
                col(ResourceGroupRecord.resource_id).in_(identifiers),
            )
        )
        names = await session.exec(
            select(col(UserRecord.id), col(UserRecord.name)).where(
                col(UserRecord.id).in_([one.owner_id for one in records])
            )
        )
        by_skill: dict[UUID, list[SkillVersion]] = {one: [] for one in identifiers}
        for version in versions.all():
            by_skill[version.skill_id].append(_to_version(version))
        shared: dict[UUID, list[str]] = {one: [] for one in identifiers}
        for row in groups.all():
            shared[row.resource_id].append(row.group_id.hex)
        owner_name = dict(names.all())
        return [
            SkillDetail(
                skill=_to_skill(one),
                owner_name=owner_name.get(one.owner_id, ""),
                versions=by_skill[one.id],
                group_ids=sorted(shared[one.id]),
            )
            for one in records
        ]

    def _available_statement(self, user_id: UUID) -> Select[tuple[object, ...]]:
        released = _latest_released()
        approved = _latest_approved()
        mine = col(SkillRecord.owner_id) == user_id
        group_shared = (col(SkillRecord.visibility) == Visibility.GROUP) & _shared_with(user_id)
        first_hand = (mine | group_shared) & released.c.version_id.is_not(None)
        in_catalog = approved.c.version_id.is_not(None)
        return (
            _listing_select(
                description=case((first_hand, released.c.description), else_=approved.c.description),
                version=case((first_hand, released.c.version), else_=approved.c.version),
                file_count=case((first_hand, released.c.file_count), else_=approved.c.file_count),
                total_bytes=case((first_hand, released.c.total_bytes), else_=approved.c.total_bytes),
                source=case(
                    (mine, SkillSource.OWNED.value),
                    (group_shared, SkillSource.GROUP.value),
                    else_=SkillSource.CATALOG.value,
                ),
            )
            .join(UserRecord, onclause=col(UserRecord.id) == col(SkillRecord.owner_id))
            .outerjoin(released, onclause=released.c.skill_id == col(SkillRecord.id))
            .outerjoin(approved, onclause=approved.c.skill_id == col(SkillRecord.id))
            .where(col(SkillRecord.is_deleted).is_(False), first_hand | in_catalog)
        )

    async def _listing(self, statement: Select[tuple[object, ...]]) -> list[SkillListing]:
        async with self._engine.connect() as connection:
            found = (await connection.execute(statement)).mappings().all()
        return [
            SkillListing(
                id=row["id"].hex,
                owner_id=row["owner_id"].hex,
                owner_name=row["owner_name"],
                name=row["name"],
                description=row["description"],
                subject=row["subject"],
                visibility=row["visibility"],
                call_count=row["call_count"],
                version=row["version"],
                file_count=row["file_count"],
                total_bytes=row["total_bytes"],
                source=SkillSource(row["source"]),
                updated_at=row["updated_at"],
            )
            for row in found
        ]


def _listing_select(
    *,
    description: ColumnElement[str],
    version: ColumnElement[int],
    file_count: ColumnElement[int],
    total_bytes: ColumnElement[int],
    source: ColumnElement[str],
) -> Select[tuple[object, ...]]:
    return sa_select(
        col(SkillRecord.id).label("id"),
        col(SkillRecord.owner_id).label("owner_id"),
        col(UserRecord.name).label("owner_name"),
        col(SkillRecord.name).label("name"),
        description.label("description"),
        col(SkillRecord.subject).label("subject"),
        col(SkillRecord.visibility).label("visibility"),
        col(SkillRecord.call_count).label("call_count"),
        version.label("version"),
        file_count.label("file_count"),
        total_bytes.label("total_bytes"),
        source.label("source"),
        col(SkillRecord.updated_at).label("updated_at"),
    )


def _version_select() -> Select[VersionRow]:
    return sa_select(
        col(SkillVersionRecord.skill_id).label("skill_id"),
        col(SkillVersionRecord.id).label("version_id"),
        col(SkillVersionRecord.version).label("version"),
        col(SkillVersionRecord.description).label("description"),
        col(SkillVersionRecord.file_count).label("file_count"),
        col(SkillVersionRecord.total_bytes).label("total_bytes"),
        col(SkillVersionRecord.released_at).label("released_at"),
    )


def _latest_released() -> Subquery:
    return _latest(_version_select().where(col(SkillVersionRecord.status) == VersionStatus.RELEASED))


def _latest_approved() -> Subquery:
    return _latest(
        _version_select()
        .join(ReviewRecord, onclause=col(ReviewRecord.target_id) == col(SkillVersionRecord.id))
        .where(
            col(ReviewRecord.target_kind) == ResourceKind.SKILL,
            col(ReviewRecord.status) == ReviewStatus.APPROVED,
        )
    )


def _latest(statement: Select[VersionRow]) -> Subquery:
    return (
        statement.distinct(col(SkillVersionRecord.skill_id))
        .order_by(col(SkillVersionRecord.skill_id), col(SkillVersionRecord.version).desc())
        .subquery()
    )


def _shared_with(user_id: UUID) -> ColumnElement[bool]:
    return exists(
        sa_select(1)
        .select_from(ResourceGroupRecord)
        .join(GroupMemberRecord, onclause=col(GroupMemberRecord.group_id) == col(ResourceGroupRecord.group_id))
        .where(
            col(ResourceGroupRecord.resource_kind) == ResourceKind.SKILL,
            col(ResourceGroupRecord.resource_id) == col(SkillRecord.id),
            col(GroupMemberRecord.user_id) == user_id,
        )
    )


def _parse(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None


def _to_skill(record: SkillRecord) -> Skill:
    return Skill(
        id=record.id.hex,
        owner_id=record.owner_id.hex,
        name=record.name,
        subject=record.subject,
        visibility=record.visibility,
        call_count=record.call_count,
        is_deleted=record.is_deleted,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _to_version(record: SkillVersionRecord) -> SkillVersion:
    return SkillVersion(
        id=record.id.hex,
        version=record.version,
        status=record.status,
        description=record.description,
        file_count=record.file_count,
        total_bytes=record.total_bytes,
        created_at=record.created_at,
        released_at=record.released_at,
    )
