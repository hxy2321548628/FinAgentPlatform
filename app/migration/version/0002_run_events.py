"""建 run_events 表

Revision ID: 0002_run_events
Revises: 0001_runs
Create Date: 2026-08-07
"""

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_run_events"
down_revision: str | None = "0001_runs"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """建表 / 改表。"""
    op.create_table(
        "run_events",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        # 事件 id 的 `{毫秒}-{序号}` 打包成一个可排序的整数，见 run/archive.py 的 pack
        sa.Column("seq", sa.BigInteger(), nullable=False),
        sa.Column("type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        # 主键就是唯一的查询模式：按 run 顺序重放。架构 §6.2 因此不给它单独建索引
        sa.PrimaryKeyConstraint("run_id", "seq"),
    )
    # 保留期清理按时间扫，没有这条索引它会全表扫
    op.create_index("ix_run_events_ts", "run_events", ["ts"])


def downgrade() -> None:
    """回滚上面那一步。"""
    op.drop_index("ix_run_events_ts", table_name="run_events")
    op.drop_table("run_events")
