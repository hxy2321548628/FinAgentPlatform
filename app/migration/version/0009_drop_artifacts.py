"""删掉 artifacts 表

Revision ID: 0009_drop_artifacts
Revises: 0008_thread_history
Create Date: 2026-08-12

产物存储整条撤掉：字节随会话工作目录一起走，取回它们的唯一一条路是
`/api/threads/{id}/files/raw`。这张表记的是「某次 run 认领过的东西」在对象存储里的
键，而对象存储已经不再存产物 —— 留着就是一张指向不存在对象的索引。

**表里的行直接丢，不迁移。** 它们唯一的用处是把事件里的主键换成 `s3_key`，
而事件那一侧也已经不再报产物了。保留期内的历史 `run.finished` 仍带着 `artifacts`
字段，那是不可变日志的应有之义 —— 事件模型按忽略多余字段处理，读回来不会失败，
只是那些标识不再对应任何可下载的东西。

`downgrade` 只把表建回来，**行找不回来** —— 那些键指向的对象在 MinIO 里也一并
清掉了，回填等于编一批指向不存在对象的行。
"""

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op

revision: str = "0009_drop_artifacts"
down_revision: str | None = "0008_thread_history"
branch_labels: str | None = None
depends_on: str | None = None

TABLE_NAME = "artifacts"
RUN_INDEX = "ix_artifacts_run"


def upgrade() -> None:
    """删表。"""
    op.drop_index(RUN_INDEX, table_name=TABLE_NAME)
    op.drop_table(TABLE_NAME)


def downgrade() -> None:
    """把表建回来，空的。"""
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
