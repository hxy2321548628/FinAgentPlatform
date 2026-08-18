"""给 Agent 与 Skill 增加平台目录上下架闸门。

Revision ID: 0016_catalog_lifecycle
Revises: 0015_user_email_dept
Create Date: 2026-08-18

审核记录是不可改写的历史。下架只改资源当前是否进入平台目录，
不把 approved 改成其他状态，否则既会丢审核留痕，也可能让更早的过审版本重新露出。
"""

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op

from app.preset.model import TABLE_NAME as AGENT_TABLE_NAME
from app.preset.skill import TABLE_NAME as SKILL_TABLE_NAME

revision: str = "0016_catalog_lifecycle"
down_revision: str | None = "0015_user_email_dept"
branch_labels: str | None = None
depends_on: str | None = None

CATALOG_DISABLED_BY_FK = {
    AGENT_TABLE_NAME: "fk_agents_catalog_disabled_by",
    SKILL_TABLE_NAME: "fk_skills_catalog_disabled_by",
}


def upgrade() -> None:
    """增加目录闸门与下架留痕。"""
    for table_name in (AGENT_TABLE_NAME, SKILL_TABLE_NAME):
        op.add_column(
            table_name,
            sa.Column("catalog_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        )
        op.add_column(
            table_name,
            sa.Column("catalog_disabled_reason", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        )
        op.add_column(table_name, sa.Column("catalog_disabled_by", sa.Uuid(), nullable=True))
        op.add_column(
            table_name,
            sa.Column("catalog_disabled_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_foreign_key(
            CATALOG_DISABLED_BY_FK[table_name],
            table_name,
            "users",
            ["catalog_disabled_by"],
            ["id"],
        )


def downgrade() -> None:
    """移除目录闸门与下架留痕。"""
    for table_name in (SKILL_TABLE_NAME, AGENT_TABLE_NAME):
        op.drop_constraint(CATALOG_DISABLED_BY_FK[table_name], table_name, type_="foreignkey")
        op.drop_column(table_name, "catalog_disabled_at")
        op.drop_column(table_name, "catalog_disabled_by")
        op.drop_column(table_name, "catalog_disabled_reason")
        op.drop_column(table_name, "catalog_enabled")
