"""建 groups / user_groups / group_join_requests 三张表

Revision ID: 0007_group
Revises: 0006_artifacts
Create Date: 2026-08-11

**只建表，不给已有账号编组。** 这一版之前的用户都不属于任何组，那是真实情况而不是
待回填的空缺 —— 组是从这一版才开始有的东西。

待审批的申请用**条件唯一索引**而不是普通唯一索引：`(group_id, user_id)` 全表唯一的话，
一个学生被否决之后就再也申请不了同一个组，而那是把人永久挡在门外，不是本意。
"""

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op

from group.model import (
    MEMBER_GROUP_INDEX,
    MEMBER_TABLE_NAME,
    PENDING_REQUEST_CONDITION,
    PENDING_REQUEST_INDEX,
    REQUEST_TABLE_NAME,
    TABLE_NAME,
)

revision: str = "0007_group"
down_revision: str | None = "0006_artifacts"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """建表。"""
    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("invite_code", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name="fk_groups_owner"),
        sa.UniqueConstraint("name", name="uq_groups_name"),
        sa.UniqueConstraint("invite_code", name="uq_groups_invite_code"),
    )

    op.create_table(
        MEMBER_TABLE_NAME,
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "group_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_user_groups_user"),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], name="fk_user_groups_group"),
    )
    # 反查组成员。另一个方向「我在哪些组」已由主键前缀覆盖
    op.create_index(MEMBER_GROUP_INDEX, MEMBER_TABLE_NAME, ["group_id"])

    op.create_table(
        REQUEST_TABLE_NAME,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], name="fk_group_join_requests_group"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_group_join_requests_user"),
    )
    # 同一个人在同一个组里只能挂着一条待审批，但被否决之后可以再来
    op.create_index(
        PENDING_REQUEST_INDEX,
        REQUEST_TABLE_NAME,
        ["group_id", "user_id"],
        unique=True,
        postgresql_where=sa.text(PENDING_REQUEST_CONDITION),
    )


def downgrade() -> None:
    """回滚上面那一步。"""
    op.drop_index(PENDING_REQUEST_INDEX, table_name=REQUEST_TABLE_NAME)
    op.drop_table(REQUEST_TABLE_NAME)
    op.drop_index(MEMBER_GROUP_INDEX, table_name=MEMBER_TABLE_NAME)
    op.drop_table(MEMBER_TABLE_NAME)
    op.drop_table(TABLE_NAME)
