"""建 mcp_servers，并给 agent_versions 增加 mcp_refs。

Revision ID: 0014_mcp_catalog
Revises: 0013_agent_subagents
Create Date: 2026-08-16

迁移只追加结构，不回填。历史 agent 版本的 `mcp_refs` 保持 NULL，准确表示当时还没有
MCP 引用能力。`reviews` 不改列，只新增应用层枚举取值 `mcp`。

**`mcp_servers` 没有版本表，这不是遗漏。** 那台机器上的内容不在平台手里，冻不住，
一条记录就是「上架时它长这样」的一份快照 —— 详见 `preset/mcp.py`。
"""

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op
from sqlalchemy.dialects import postgresql

from app.preset.mcp import MCP_NAME_CONDITION, MCP_NAME_INDEX, TABLE_NAME

revision: str = "0014_mcp_catalog"
down_revision: str | None = "0013_agent_subagents"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """增加 MCP 目录结构。"""
    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("description", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("url", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("transport", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("credential_key", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("tool_names", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("latency_note", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("stores_user_data", sa.Boolean(), nullable=False),
        sa.Column("sends_data_out", sa.Boolean(), nullable=False),
        sa.Column("has_write_operation", sa.Boolean(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("disabled_reason", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("submitted_by", sa.Uuid(), nullable=False),
        sa.Column("reviewed_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["submitted_by"], ["users.id"], name="fk_mcp_servers_submitter"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], name="fk_mcp_servers_reviewer"),
    )
    op.create_index(
        MCP_NAME_INDEX,
        TABLE_NAME,
        ["name"],
        unique=True,
        postgresql_where=sa.text(MCP_NAME_CONDITION),
    )

    op.add_column(
        "agent_versions",
        sa.Column("mcp_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    """移除 MCP 目录结构。"""
    op.drop_column("agent_versions", "mcp_refs")
    op.drop_index(MCP_NAME_INDEX, table_name=TABLE_NAME)
    op.drop_table(TABLE_NAME)
