"""Thread workspace 最终清理任务的数据形状。"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import Index, text
from sqlmodel import Field, SQLModel

TABLE_NAME = "thread_purge_jobs"


class ThreadPurgeRecord(SQLModel, table=True):
    """一个软删 thread 的可重试物理清理记录。"""

    __tablename__ = TABLE_NAME
    __table_args__ = (
        Index(
            "ix_thread_purge_pending",
            "requested_at",
            postgresql_where=text("completed_at IS NULL"),
        ),
    )

    thread_id: UUID = Field(primary_key=True, foreign_key="threads.id")
    requested_at: datetime
    completed_at: datetime | None = Field(default=None)
    attempts: int = Field(default=0)
    last_error: str | None = Field(default=None)


@dataclass(frozen=True)
class PurgeJob:
    """待执行的 workspace 清理任务。"""

    thread_id: str
    requested_at: datetime
    attempts: int
    last_error: str | None
