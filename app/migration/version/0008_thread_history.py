"""给 runs 补提问原文，给 threads 补删除标记

Revision ID: 0008_thread_history
Revises: 0007_group
Create Date: 2026-08-11

**`runs.content` 是聊天历史的用户那一侧。** 在这一版之前提问只随任务消息走，跑完就
没了 —— 事件流里也没有承载它的事件，因此把一个 run 的事件全部重放一遍，重建出来的
对话只有 agent 那一半。加这一列之前，「翻看以前问过什么」是做不到的。

历史行在这一列上是 NULL，那是遗留而不是待回填的空缺：那些提问已经不存在于任何地方
（checkpoint 里的 messages 是框架自建表，保留期比 runs 短得多，且它不是业务的真相源）。

**`threads.deleted_at` 让删会话成为软删除。** 硬删会撞上 `runs.thread_id` 的外键，
而顺着删掉 runs 等于把成本账本挖掉一块 —— 数据设计里 `runs` 是明确「不清」的那张表，
它是历史的索引。教师删会话要的是「从我的列表里消失、别再占磁盘」，不是「抹掉平台的账」：
因此这一列只管前者，workspace 目录仍然真删。
"""

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op

revision: str = "0008_thread_history"
down_revision: str | None = "0007_group"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """加两列。"""
    op.add_column("runs", sa.Column("content", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column("threads", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """回滚上面那一步。"""
    op.drop_column("threads", "deleted_at")
    op.drop_column("runs", "content")
