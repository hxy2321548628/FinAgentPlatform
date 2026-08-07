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
    thread_id: UUID = Field(index=False, foreign_key="threads.id")
    # P2 之前建的行在这一列上是空的：那批 run 没有真实归属，编一个 owner 只会造假数据。
    # 空值因此是遗留而不是 bug，见 migration/version/0003_user_thread.py
    user_id: UUID | None = Field(default=None, foreign_key="users.id")
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

    async def create(self, *, run_id: str, thread_id: str, user_id: str) -> None:
        """记下一个刚提交、还没开跑的 run。

        `user_id` 是有意的反范式（严格范式下它该经 `threads` 推导）：配额统计与隔离
        过滤两条高频路径都要按用户聚合，每次都 join 不值得。一致性由这个唯一入口
        保证 —— 而调用方在提交之前已经用同一个 `user_id` 查过 thread，查不到就走不到这里。
        """
        record = RunRecord(
            id=UUID(run_id),
            thread_id=UUID(thread_id),
            user_id=UUID(user_id),
            status=RunStatus.QUEUED,
            started_at=datetime.now(UTC),
        )
        async with AsyncSession(self._engine) as session:
            session.add(record)
            await session.commit()

    async def get(self, run_id: str, *, user_id: str) -> Run | None:
        """按 id 查一次 run，**只查得到自己的那些**。

        别人的 run 与不存在的 run 在这里是同一个结果，端点因此自然落到 404。

        Args:
            run_id: run 标识。
            user_id: 当前用户。

        Returns:
            找到的 run；不存在、id 不合法，或不属于该用户则 None。
        """
        identifier, owner = _parse(run_id), _parse(user_id)
        if identifier is None or owner is None:
            return None
        async with AsyncSession(self._engine) as session:
            record = await session.get(RunRecord, identifier)
        if record is None or record.user_id != owner:
            return None
        return record.to_run()

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

        **这是本类里唯一不带 user 上下文的查询**，因为它不服务任何用户请求：
        崩溃恢复扫的是「此刻还没跑完的 run」，调用方是 worker 的启动路径，
        那里根本没有登录用户。走 `ix_runs_unfinished` 那条部分索引。

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


def _parse(identifier: str) -> UUID | None:
    """标识来自 URL 与 session，属于不可信输入 —— 解析不了就是「查不到」，不是 500。"""
    try:
        return UUID(identifier)
    except ValueError:
        return None
