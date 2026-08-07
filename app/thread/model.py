"""会话的数据形状：`threads` 表的结构。

**这张表是「会话存不存在」的权威，workspace 目录是它的副产品。** 建了表之后同一个
问题有两个答案（表里有没有、目录在不在），而两者会分叉 —— 目录被误删、或建表成功
但建目录失败。选表作权威是因为多租户隔离的过滤条件长在表上，而目录没有归属信息：
让目录当权威，等于把越权检查建在一个不知道谁是主人的东西上。

broker 那边的 `/exists` 保留，但降级为 broker 自己的视角（它管容器与目录，本来就该
有一个），api 侧不再调用它。
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Index, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Column, Field, SQLModel

TABLE_NAME = "threads"


class ThreadRecord(SQLModel, table=True):
    """`threads` 表的一行。"""

    __tablename__ = TABLE_NAME
    # 会话列表按 `updated_at DESC` 翻页，且永远带着 `user_id` 过滤条件
    __table_args__ = (Index("ix_threads_user_updated", "user_id", text("updated_at DESC")),)

    id: UUID = Field(primary_key=True)
    user_id: UUID = Field(foreign_key="users.id")
    title: str = Field(default="")
    # 整体读写的配置块，从不按字段查询，且后续方向（自定义提示词、skill、MCP）
    # 会持续往里加字段。拆成列意味着每加一个功能就要迁移一次
    agent_config: dict[str, object] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    created_at: datetime
    updated_at: datetime
