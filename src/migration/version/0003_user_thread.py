"""建 users 与 threads 两张表，并给 runs 补上外键

Revision ID: 0003_user_thread
Revises: 0002_run_events
Create Date: 2026-08-08

**只建表，不回填已有数据。** 迁移之前的 `runs` 行与 workspace 目录全部是验收脚本
跑出来的，没有真实归属 —— 给它们编一个 owner 只会造出一批假数据。因此本次迁移之后
`runs.user_id` 仍有一批空值，那是遗留而不是 bug；已有的 workspace 目录成为孤儿目录，
由 deploy/workspace-report.sh 可见，人工清理。

`runs.user_id` 的外键这一版就建：遗留行在这一列上是 NULL，而 NULL 本来就不受外键约束。

**`runs.thread_id` 的外键不在这一版**，它在 0004 —— 建表的这一刻 `threads` 还是空的，
而提交 run 的入口此时仍只建目录不落表，外键一加，每一次提交都会当场炸在插入上。
等隔离那一步让 api 先落 `threads` 行之后再加，那时它才约束得住真实的写入路径。
"""

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_user_thread"
down_revision: str | None = "0002_run_events"
branch_labels: str | None = None
depends_on: str | None = None

RUN_USER_FOREIGN_KEY = "fk_runs_user"


def upgrade() -> None:
    """建表 / 改表。"""
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("password_hash", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("role", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        # 留空表示「跟着角色的默认档走」，不是「没有配额」，见 user/model.py
        sa.Column("quota_tokens_daily", sa.Integer(), nullable=True),
        sa.Column("quota_concurrent_runs", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_users_name"),
    )

    op.create_table(
        "threads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("agent_config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_threads_user"),
    )
    op.create_index("ix_threads_user_updated", "threads", ["user_id", sa.text("updated_at DESC")])

    op.create_foreign_key(RUN_USER_FOREIGN_KEY, "runs", "users", ["user_id"], ["id"])


def downgrade() -> None:
    """回滚上面那一步。"""
    op.drop_constraint(RUN_USER_FOREIGN_KEY, "runs", type_="foreignkey")
    op.drop_index("ix_threads_user_updated", table_name="threads")
    op.drop_table("threads")
    op.drop_table("users")
