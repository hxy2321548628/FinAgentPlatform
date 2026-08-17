"""建 artifacts 表

Revision ID: 0006_artifacts
Revises: 0005_run_status_value
Create Date: 2026-08-08

**只建表，不回填历史产物。** 这一版之前的产物只躺在 workspace 里，没有 `s3_key` ——
给它们编一行等于编一个指向不存在对象的键。历史事件里的旧形状标识仍然认得，
产物端点按 `/` 分辨两种形状，兼容期跟着 run_events 的 180 天保留期走。

`size` 用 bigint 而不是 int：int 列封顶 2GB，而超限是在 run 跑完之后才炸，
那时分析的钱已经花掉了。
"""

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op

revision: str = "0006_artifacts"
down_revision: str | None = "0005_run_status_value"
branch_labels: str | None = None
depends_on: str | None = None

TABLE_NAME = "artifacts"
RUN_INDEX = "ix_artifacts_run"


def upgrade() -> None:
    """建表。"""
    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("s3_key", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("mime", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], name="fk_artifacts_run"),
    )
    op.create_index(RUN_INDEX, TABLE_NAME, ["run_id"])


def downgrade() -> None:
    """回滚上面那一步。"""
    op.drop_index(RUN_INDEX, table_name=TABLE_NAME)
    op.drop_table(TABLE_NAME)
