"""建 runs 表

Revision ID: 0001_runs
Revises:
Create Date: 2026-08-07
"""

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op

revision: str = "0001_runs"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None

# 与 event.model.RunStatus 一致。写成字面量而不是导入枚举，是因为迁移是历史快照：
# 将来枚举加了值，这一版迁移仍应建出当时那个样子的部分索引
UNFINISHED_STATUS_SQL = "status IN ('queued', 'running')"


def upgrade() -> None:
    """建表 / 改表。"""
    op.create_table(
        "runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("thread_id", sa.Uuid(), nullable=False),
        # P3 才有用户体系。先留空，补列比补数据便宜
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("checkpoint_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("error_code", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("error_message", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("tokens_cache_read", sa.Integer(), nullable=False),
        sa.Column("tokens_uncached", sa.Integer(), nullable=False),
        sa.Column("tokens_output", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_runs_thread_started", "runs", ["thread_id", sa.text("started_at DESC")])
    op.create_index("ix_runs_user_started", "runs", ["user_id", "started_at"])
    # 部分索引：崩溃后扫「还没结束的 run」。全量索引会随历史无限长大，
    # 而这条查询关心的永远是很小的一撮
    op.create_index("ix_runs_unfinished", "runs", ["status"], postgresql_where=sa.text(UNFINISHED_STATUS_SQL))


def downgrade() -> None:
    """回滚上面那一步。"""
    op.drop_index("ix_runs_unfinished", table_name="runs")
    op.drop_index("ix_runs_user_started", table_name="runs")
    op.drop_index("ix_runs_thread_started", table_name="runs")
    op.drop_table("runs")
