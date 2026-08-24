"""增加 thread 私有记忆的 outbox、用量账与 workspace 清理补偿。

Revision ID: 0017_memory
Revises: 0016_catalog_lifecycle
Create Date: 2026-08-21
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.memory.job import MEMORY_JOB_TABLE, MEMORY_USAGE_TABLE
from app.thread.purge import TABLE_NAME as PURGE_TABLE

revision: str = "0017_memory"
down_revision: str | None = "0016_catalog_lifecycle"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """建立 P15 任务与审计表，记忆正文仍只在 memdir。"""
    op.add_column("runs", sa.Column("user_context", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.create_table(
        MEMORY_JOB_TABLE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("thread_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accepted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "rejection_reasons",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], name="fk_memory_jobs_run"),
        sa.ForeignKeyConstraint(["thread_id"], ["threads.id"], name="fk_memory_jobs_thread"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_memory_jobs_user"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", name="uq_memory_jobs_run"),
    )
    op.create_index(
        "ix_memory_jobs_queued",
        MEMORY_JOB_TABLE,
        ["status", "created_at"],
        postgresql_where=sa.text("status = 'queued'"),
    )
    op.create_table(
        MEMORY_USAGE_TABLE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("thread_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("stage", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("tokens_cache_read", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_uncached", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_output", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_yuan", sa.Float(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fallback_reason", sa.Text(), nullable=True),
        sa.Column("included_in_run", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "selected_slugs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], name="fk_memory_usage_run"),
        sa.ForeignKeyConstraint(["thread_id"], ["threads.id"], name="fk_memory_usage_thread"),
        sa.ForeignKeyConstraint(["job_id"], [f"{MEMORY_JOB_TABLE}.id"], name="fk_memory_usage_job"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "stage", name="uq_memory_usage_run_stage"),
    )
    op.create_index("ix_memory_usage_thread_created", MEMORY_USAGE_TABLE, ["thread_id", "created_at"])
    op.create_table(
        PURGE_TABLE,
        sa.Column("thread_id", sa.Uuid(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["thread_id"], ["threads.id"], name="fk_thread_purge_thread"),
        sa.PrimaryKeyConstraint("thread_id"),
    )
    op.create_index(
        "ix_thread_purge_pending",
        PURGE_TABLE,
        ["requested_at"],
        postgresql_where=sa.text("completed_at IS NULL"),
    )


def downgrade() -> None:
    """移除 P15 任务与审计表。"""
    op.drop_index("ix_thread_purge_pending", table_name=PURGE_TABLE)
    op.drop_table(PURGE_TABLE)
    op.drop_index("ix_memory_usage_thread_created", table_name=MEMORY_USAGE_TABLE)
    op.drop_table(MEMORY_USAGE_TABLE)
    op.drop_index("ix_memory_jobs_queued", table_name=MEMORY_JOB_TABLE)
    op.drop_table(MEMORY_JOB_TABLE)
    op.drop_column("runs", "user_context")
