"""Skill 目录的数据形状与基础仓储。

Skill 与智能体共用可见性、版本状态、共享和审核流程，但内容形状不同：身份行固定
`name`，版本行保存会随上传变化的说明与文件统计。已发布版本只追加，不原地改。
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Index, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import Field, SQLModel, col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from preset.model import FIRST_VERSION, VersionStatus, Visibility, _value_enum

TABLE_NAME = "skills"
VERSION_TABLE_NAME = "skill_versions"

SKILL_NAME_INDEX = "ux_skills_owner_name"
SKILL_OWNER_INDEX = "ix_skills_owner"
VERSION_NUMBER_INDEX = "ux_skill_versions_number"
DRAFT_VERSION_INDEX = "ux_skill_versions_draft"

SKILL_NAME_CONDITION = "is_deleted = false"
DRAFT_VERSION_CONDITION = "status = 'draft'"

logger = logging.getLogger(__name__)


class SkillRecord(SQLModel, table=True):
    """`skills` 表的一行：一个 skill 的稳定身份。"""

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
    """`skill_versions` 表的一行：一个不可变的上传版本。"""

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


@dataclass(frozen=True)
class Skill:
    """一个 skill 的稳定身份。"""

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
    """一个 skill 版本的元信息。"""

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
    """作者视角的 skill 身份与全部版本。"""

    skill: Skill
    versions: list[SkillVersion]


class SkillRepository:
    """`skills` 与 `skill_versions` 的基础读写。

    Args:
        engine: 到 Postgres 的异步引擎。
    """

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
        """建 skill 身份行与 v1 草稿。

        Args:
            owner_id: 作者。
            name: frontmatter 中的稳定标识。
            subject: 学科。
            description: v1 的 frontmatter 说明。
            file_count: v1 文件数。
            total_bytes: v1 文件总字节数。

        Returns:
            建出的 skill；同一作者已有同名未删除 skill 时返回 None。
        """
        now = datetime.now(UTC)
        record = SkillRecord(
            id=uuid4(),
            owner_id=UUID(owner_id),
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
        logger.info("建 skill：skill_id=%s owner_id=%s", record.id.hex, owner_id)
        return _to_skill(record)

    async def detail(self, skill_id: str, *, owner_id: str) -> SkillDetail | None:
        """读取一个属于当前作者的 skill 及全部版本。

        Args:
            skill_id: Skill 标识。
            owner_id: 当前作者。

        Returns:
            Skill 全貌；不存在、标识无效或不属于当前作者时返回 None。
        """
        identifier = _parse(skill_id)
        owner = _parse(owner_id)
        if identifier is None or owner is None:
            return None
        async with AsyncSession(self._engine) as session:
            record = await session.get(SkillRecord, identifier)
            if record is None or record.owner_id != owner:
                return None
            found = await session.exec(
                select(SkillVersionRecord)
                .where(col(SkillVersionRecord.skill_id) == identifier)
                .order_by(col(SkillVersionRecord.version))
            )
            versions = [_to_version(one) for one in found.all()]
        return SkillDetail(skill=_to_skill(record), versions=versions)


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
