"""给 runs 补当次实际生效的 agent 配置快照

Revision ID: 0010_run_agent_config
Revises: 0009_drop_artifacts
Create Date: 2026-08-14

历史 run 保持 NULL：它们执行时自定义配置还没有接入装配层，NULL 与空配置
都如实表示「使用平台默认」。
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_run_agent_config"
down_revision: str | None = "0009_drop_artifacts"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """增加可空的 run 配置快照。"""
    op.add_column(
        "runs",
        sa.Column("agent_config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    """删除 run 配置快照。"""
    op.drop_column("runs", "agent_config")
