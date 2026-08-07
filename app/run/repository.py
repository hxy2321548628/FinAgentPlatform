"""run 元数据的落库：`runs` 表的结构与读写。

**这张表存在的理由是进程边界**。P1 之前 run 的状态是执行器内存里的一个 dict，
而 worker 拆出去之后那个 dict 在 worker 进程里，查询请求却打在 api 进程上 ——
`GET /runs/{id}` 会直接失效。落库之后两个进程看到的是同一份。

表结构由 Alembic 管（`migration/`），不在这里 `create_all` —— 两条路都能建表时，
它们迟早会分叉。
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Index, text
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import Field, SQLModel, col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from event.model import RunErrorCode, RunStatus, TokenUsage

logger = logging.getLogger(__name__)

TABLE_NAME = "runs"

# 崩溃后要接着跑的就是这两态。部分索引只覆盖它们 —— 全量索引会随历史 run 无限长大，
# 而这条查询只关心「此刻还没结束的」，那永远是很小的一撮
UNFINISHED_STATUS = (RunStatus.QUEUED, RunStatus.RUNNING)


@dataclass(frozen=True)
class Run:
    """一次提问的执行记录。

    **不带教师的问题**：那个字段只在提交到执行之间用得着，随任务消息走，不必落库。
    """

    id: str
    thread_id: str
    status: RunStatus


class RunRecord(SQLModel, table=True):
    """`runs` 表的一行。"""

    __tablename__ = TABLE_NAME
    __table_args__ = (
        Index("ix_runs_thread_started", "thread_id", text("started_at DESC")),
        Index("ix_runs_user_started", "user_id", "started_at"),
        Index(
            "ix_runs_unfinished",
            "status",
            postgresql_where=text("status IN ('queued', 'running')"),
        ),
    )

    id: UUID = Field(primary_key=True)
    thread_id: UUID = Field(index=False)
    # P3 才有用户体系。留空而不是不建，是因为补列比补数据便宜
    user_id: UUID | None = Field(default=None)
    status: RunStatus
    # 架构 §6.2 的草案里有这一列，本期没有写它的人：恢复靠 thread_id 找最新的
    # checkpoint，不指定具体某一个
    checkpoint_id: str | None = Field(default=None)
    error_code: RunErrorCode | None = Field(default=None)
    error_message: str | None = Field(default=None)
    tokens_cache_read: int = Field(default=0)
    tokens_uncached: int = Field(default=0)
    tokens_output: int = Field(default=0)
    started_at: datetime
    ended_at: datetime | None = Field(default=None)

    def to_run(self) -> Run:
        """转成执行器与端点认的那个形状。"""
        return Run(id=self.id.hex, thread_id=self.thread_id.hex, status=self.status)


class RunRepository:
    """`runs` 表的读写。

    Args:
        engine: 到 Postgres 的异步引擎。
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def create(self, *, run_id: str, thread_id: str) -> None:
        """记下一个刚提交、还没开跑的 run。"""
        record = RunRecord(
            id=UUID(run_id),
            thread_id=UUID(thread_id),
            status=RunStatus.QUEUED,
            started_at=datetime.now(UTC),
        )
        async with AsyncSession(self._engine) as session:
            session.add(record)
            await session.commit()

    async def get(self, run_id: str) -> Run | None:
        """按 id 查一次 run，不存在或 id 不是合法 uuid 时返回 None。"""
        identifier = _parse(run_id)
        if identifier is None:
            return None
        async with AsyncSession(self._engine) as session:
            record = await session.get(RunRecord, identifier)
            return None if record is None else record.to_run()

    async def start(self, run_id: str) -> None:
        """标记开跑。"""
        await self._update(run_id, status=RunStatus.RUNNING)

    async def succeed(self, run_id: str, *, tokens: TokenUsage) -> None:
        """标记跑完，并记下这一次的 token 消耗。"""
        await self._update(
            run_id,
            status=RunStatus.SUCCEEDED,
            ended_at=datetime.now(UTC),
            tokens_cache_read=tokens.input_cache_read,
            tokens_uncached=tokens.input_uncached,
            tokens_output=tokens.output,
        )

    async def fail(self, run_id: str, *, code: RunErrorCode, message: str) -> None:
        """标记失败，并记下原因。"""
        await self._update(
            run_id,
            status=RunStatus.FAILED,
            ended_at=datetime.now(UTC),
            error_code=code,
            error_message=message,
        )

    async def unfinished(self) -> list[Run]:
        """列出还没走到终态的 run。

        崩溃恢复扫的就是它，走 `ix_runs_unfinished` 那条部分索引。

        Returns:
            状态为 `queued` 或 `running` 的 run，按提交顺序。
        """
        async with AsyncSession(self._engine) as session:
            statement = (
                select(RunRecord)
                .where(col(RunRecord.status).in_(UNFINISHED_STATUS))
                .order_by(col(RunRecord.started_at))
            )
            found = await session.exec(statement)
            return [record.to_run() for record in found.all()]

    async def _update(self, run_id: str, **change: object) -> None:
        """改一行的若干列。目标行不存在时记警告后返回 —— 状态流转不该把 run 打断。"""
        identifier = _parse(run_id)
        if identifier is None:
            logger.warning("run id 不是合法 uuid，状态未落库：run_id=%s", run_id)
            return
        async with AsyncSession(self._engine) as session:
            record = await session.get(RunRecord, identifier)
            if record is None:
                logger.warning("run 不在库里，状态未落库：run_id=%s", run_id)
                return
            for name, value in change.items():
                setattr(record, name, value)
            session.add(record)
            await session.commit()


def _parse(run_id: str) -> UUID | None:
    """Run id 来自 URL，属于不可信输入 —— 解析不了就是「查不到」，不是 500。"""
    try:
        return UUID(run_id)
    except ValueError:
        return None
