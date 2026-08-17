"""建 skills / skill_versions，并给 agent_versions 增加 skill_refs。

Revision ID: 0012_skill_catalog
Revises: 0011_agent_catalog
Create Date: 2026-08-14

迁移只追加结构，不回填。历史 agent 版本的 `skill_refs` 保持 NULL，准确表示当时还没有
skill 引用能力。`reviews` 与 `resource_groups` 不改列，只新增应用层枚举取值。
"""

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op
from sqlalchemy.dialects import postgresql

from src.app.preset.skill import (
    DRAFT_VERSION_CONDITION,
    DRAFT_VERSION_INDEX,
    SKILL_NAME_CONDITION,
    SKILL_NAME_INDEX,
    SKILL_OWNER_INDEX,
    TABLE_NAME,
    VERSION_NUMBER_INDEX,
    VERSION_TABLE_NAME,
)

revision: str = "0012_skill_catalog"
down_revision: str | None = "0011_agent_catalog"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """增加 skill 目录结构。"""
    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("subject", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("visibility", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("call_count", sa.Integer(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name="fk_skills_owner"),
    )
    op.create_index(SKILL_OWNER_INDEX, TABLE_NAME, ["owner_id"])
    op.create_index(
        SKILL_NAME_INDEX,
        TABLE_NAME,
        ["owner_id", "name"],
        unique=True,
        postgresql_where=sa.text(SKILL_NAME_CONDITION),
    )

    op.create_table(
        VERSION_TABLE_NAME,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("skill_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("description", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("file_count", sa.Integer(), nullable=False),
        sa.Column("total_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], name="fk_skill_versions_skill"),
    )
    op.create_index(VERSION_NUMBER_INDEX, VERSION_TABLE_NAME, ["skill_id", "version"], unique=True)
    op.create_index(
        DRAFT_VERSION_INDEX,
        VERSION_TABLE_NAME,
        ["skill_id"],
        unique=True,
        postgresql_where=sa.text(DRAFT_VERSION_CONDITION),
    )

    op.add_column(
        "agent_versions",
        sa.Column("skill_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    """移除 skill 目录结构。"""
    op.drop_column("agent_versions", "skill_refs")
    op.drop_index(DRAFT_VERSION_INDEX, table_name=VERSION_TABLE_NAME)
    op.drop_index(VERSION_NUMBER_INDEX, table_name=VERSION_TABLE_NAME)
    op.drop_table(VERSION_TABLE_NAME)
    op.drop_index(SKILL_NAME_INDEX, table_name=TABLE_NAME)
    op.drop_index(SKILL_OWNER_INDEX, table_name=TABLE_NAME)
    op.drop_table(TABLE_NAME)
