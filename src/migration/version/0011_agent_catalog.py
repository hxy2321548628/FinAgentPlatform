"""建 agents / agent_versions / reviews / resource_groups 四张表

Revision ID: 0011_agent_catalog
Revises: 0010_run_agent_config
Create Date: 2026-08-14

**只建表，不回填。** 这一版之前没有任何智能体目录，历史 run 的 `agent_config` 里
也不会有 `agent_id` —— 那是真实情况，不是待补的空缺。

三条**部分唯一索引**各挡一件事，都不能改成全表唯一：

- `(owner_id, name)` 只在没删掉的那些之间唯一 —— 否则删一次名字就永久占着；
- 一个 agent 同时最多一个 draft —— 否则「我在改的是哪一份」没有答案；
- 一个版本同时最多一条 pending —— 否则连点两次提审，reviewer 的队列里就是两条。
"""

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op

from src.app.preset.model import (
    AGENT_NAME_CONDITION,
    AGENT_NAME_INDEX,
    AGENT_OWNER_INDEX,
    DRAFT_VERSION_CONDITION,
    DRAFT_VERSION_INDEX,
    PENDING_REVIEW_CONDITION,
    PENDING_REVIEW_INDEX,
    RESOURCE_GROUP_TABLE_NAME,
    REVIEW_TABLE_NAME,
    REVIEW_TARGET_INDEX,
    TABLE_NAME,
    VERSION_NUMBER_INDEX,
    VERSION_TABLE_NAME,
)

revision: str = "0011_agent_catalog"
down_revision: str | None = "0010_run_agent_config"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """建表。"""
    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("description", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("subject", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("visibility", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("call_count", sa.Integer(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name="fk_agents_owner"),
    )
    op.create_index(AGENT_OWNER_INDEX, TABLE_NAME, ["owner_id"])
    op.create_index(
        AGENT_NAME_INDEX,
        TABLE_NAME,
        ["owner_id", "name"],
        unique=True,
        postgresql_where=sa.text(AGENT_NAME_CONDITION),
    )

    op.create_table(
        VERSION_TABLE_NAME,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("system_prompt", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], name="fk_agent_versions_agent"),
    )
    op.create_index(VERSION_NUMBER_INDEX, VERSION_TABLE_NAME, ["agent_id", "version"], unique=True)
    op.create_index(
        DRAFT_VERSION_INDEX,
        VERSION_TABLE_NAME,
        ["agent_id"],
        unique=True,
        postgresql_where=sa.text(DRAFT_VERSION_CONDITION),
    )

    op.create_table(
        REVIEW_TABLE_NAME,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("target_kind", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("responsibility_confirmed", sa.Boolean(), nullable=False),
        sa.Column("reason", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("submitted_by", sa.Uuid(), nullable=False),
        sa.Column("reviewed_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["submitted_by"], ["users.id"], name="fk_reviews_submitter"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], name="fk_reviews_reviewer"),
    )
    op.create_index(REVIEW_TARGET_INDEX, REVIEW_TABLE_NAME, ["target_kind", "target_id"])
    op.create_index(
        PENDING_REVIEW_INDEX,
        REVIEW_TABLE_NAME,
        ["target_kind", "target_id"],
        unique=True,
        postgresql_where=sa.text(PENDING_REVIEW_CONDITION),
    )

    # **`resource_id` 上没有外键。** 这张表按 `resource_kind` 指向不同的表，
    # 而外键只能指一张 —— 完整性由删除路径负责：软删的 agent 仍留着行，
    # 硬删不存在
    op.create_table(
        RESOURCE_GROUP_TABLE_NAME,
        sa.Column("resource_kind", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("resource_kind", "resource_id", "group_id"),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], name="fk_resource_groups_group"),
    )


def downgrade() -> None:
    """回滚上面那一步。"""
    op.drop_table(RESOURCE_GROUP_TABLE_NAME)
    op.drop_index(PENDING_REVIEW_INDEX, table_name=REVIEW_TABLE_NAME)
    op.drop_index(REVIEW_TARGET_INDEX, table_name=REVIEW_TABLE_NAME)
    op.drop_table(REVIEW_TABLE_NAME)
    op.drop_index(DRAFT_VERSION_INDEX, table_name=VERSION_TABLE_NAME)
    op.drop_index(VERSION_NUMBER_INDEX, table_name=VERSION_TABLE_NAME)
    op.drop_table(VERSION_TABLE_NAME)
    op.drop_index(AGENT_NAME_INDEX, table_name=TABLE_NAME)
    op.drop_index(AGENT_OWNER_INDEX, table_name=TABLE_NAME)
    op.drop_table(TABLE_NAME)
