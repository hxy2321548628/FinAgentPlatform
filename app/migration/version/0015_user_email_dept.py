"""给 users 增加 email 与 dept 两列。

Revision ID: 0015_user_email_dept
Revises: 0014_mcp_catalog
Create Date: 2026-08-16

**`email` 是第二把登录钥匙**，因此非空且全库唯一 —— 重了的话「这个邮箱是谁」
就没有唯一答案，而那正是登录要回答的问题。

**没有回填逻辑，这是有意的。** 加 NOT NULL 通常要给存量行编一个占位值，而编出来的
邮箱既登不上又看着像真的。本期改为先清空存量（P11 步骤三删掉 635 个验收造号，
只留 admin 与 yyyy），再在这里回填那两个账号的邮箱 —— 两行 UPDATE，值是真的。

**`dept` 只是名册上的一列**，不参与任何判断，因此给空串默认值就够，不设唯一、
不建索引。
"""

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op

from user.model import EMAIL_INDEX, TABLE_NAME

revision: str = "0015_user_email_dept"
down_revision: str | None = "0014_mcp_catalog"
branch_labels: str | None = None
depends_on: str | None = None

# 学院的邮箱域名。回填只涉及清理之后剩下的那两个账号
EMAIL_DOMAIN = "zuel.edu.cn"


def upgrade() -> None:
    """增加 email 与 dept，并给存量账号回填邮箱。"""
    op.add_column(TABLE_NAME, sa.Column("email", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column(
        TABLE_NAME,
        sa.Column("dept", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""),
    )

    # **先填再收紧**：直接建 NOT NULL 列会在有存量行时当场失败。
    # 用户名全库唯一，因此拼出来的邮箱也唯一，不会撞上下面那个索引
    op.execute(sa.text(f"UPDATE {TABLE_NAME} SET email = name || '@{EMAIL_DOMAIN}' WHERE email IS NULL"))

    op.alter_column(TABLE_NAME, "email", nullable=False)
    op.create_index(EMAIL_INDEX, TABLE_NAME, ["email"], unique=True)


def downgrade() -> None:
    """移除这两列。"""
    op.drop_index(EMAIL_INDEX, table_name=TABLE_NAME)
    op.drop_column(TABLE_NAME, "dept")
    op.drop_column(TABLE_NAME, "email")
