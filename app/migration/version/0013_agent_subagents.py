"""给 agent_versions 增加子智能体引用快照。

Revision ID: 0013_agent_subagents
Revises: 0012_skill_catalog
Create Date: 2026-08-15

迁移只追加结构，不回填。历史版本保持 NULL，准确表示发布时没有子智能体引用能力。
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_agent_subagents"
down_revision: str | None = "0012_skill_catalog"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """增加子智能体引用快照列。"""
    op.add_column(
        "agent_versions",
        sa.Column("subagent_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    """移除子智能体引用快照列。"""
    op.drop_column("agent_versions", "subagent_refs")
