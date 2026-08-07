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
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Column, Enum, Index, text, update
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import Field, SQLModel, col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from event.model import RunErrorCode, RunStatus, TokenUsage

logger = logging.getLogger(__name__)

TABLE_NAME = "runs"

# 崩溃后要接着跑的就是这两态。部分索引只覆盖它们 —— 全量索引会随历史 run 无限长大，
# 而这条查询只关心「此刻还没结束的」，那永远是很小的一撮
UNFINISHED_STATUS = (RunStatus.QUEUED, RunStatus.RUNNING)

# 还能改状态的那几态。已经走到终态的 run 再改一次是幂等的空操作，不是错误 ——
# 无论那一次写的是成功、失败还是取消。
#
# **`waiting_approval` 在里面**：它不是终态，教师在审批期间点停止、或者审批超时，
# 都要能把它转成 `cancelled`（架构 §5.4 的状态机上就有这两条边）
CANCELLABLE_STATUS = (RunStatus.QUEUED, RunStatus.RUNNING, RunStatus.WAITING_APPROVAL)


def _value_column(enum: type[StrEnum], *, nullable: bool = False) -> Column[Enum]:
    """枚举列，**按值存而不是按名字**。

    默认行为是存名字，于是库里躺着的是 `SUCCEEDED` 而事件契约与架构文档写的是
    `succeeded`。两边对不上时一声不响 —— 查询照样对（绑定参数用的是同一套编码），
    坏掉的是所有照文档写的 SQL，以及 `ix_runs_unfinished` 那条部分索引：
    它的谓词是 `status IN ('queued','running')`，永远匹配不上，于是崩溃恢复的扫描
    静默退化成全表扫。
    """
    return Column(
        Enum(enum, values_callable=lambda one: [member.value for member in one], native_enum=False),
        nullable=nullable,
    )


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
    status: RunStatus = Field(sa_column=_value_column(RunStatus))
    # 架构 §6.2 的草案里有这一列，本期没有写它的人：恢复靠 thread_id 找最新的
    # checkpoint，不指定具体某一个
    checkpoint_id: str | None = Field(default=None)
    error_code: RunErrorCode | None = Field(default=None, sa_column=_value_column(RunErrorCode, nullable=True))
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

    async def start(self, run_id: str) -> bool:
        """标记开跑。

        **同样是条件更新**：一条已经取消的 run 若因为消息重投又被领走，
        无条件写会把它从 `cancelled` 拉回 `running`，于是一次已经取消的分析
        又跑了起来 —— 而状态与事件从此对不上。

        Returns:
            这一次调用是否真的改变了状态。
        """
        return await self._transit(run_id, status=RunStatus.RUNNING)

    async def succeed(self, run_id: str, *, tokens: TokenUsage) -> bool:
        """标记跑完，并记下这一次的 token 消耗。

        Returns:
            这一次调用是否真的写下了终态。
        """
        return await self._finalize(
            run_id,
            status=RunStatus.SUCCEEDED,
            tokens_cache_read=tokens.input_cache_read,
            tokens_uncached=tokens.input_uncached,
            tokens_output=tokens.output,
        )

    async def fail(self, run_id: str, *, code: RunErrorCode, message: str) -> bool:
        """标记失败，并记下原因。

        Returns:
            这一次调用是否真的写下了终态。
        """
        return await self._finalize(run_id, status=RunStatus.FAILED, error_code=code, error_message=message)

    async def cancel(self, run_id: str, *, tokens: TokenUsage | None = None) -> bool:
        """把一个还没结束的 run 标记成取消。

        终态的 run 拿到 False，那是幂等而不是失败。

        Args:
            run_id: 目标 run。
            tokens: 取消之前已经消耗的用量，api 侧调用时没有。

        Returns:
            这一次调用是否真的改变了状态。
        """
        change: dict[str, object] = {"status": RunStatus.CANCELLED}
        if tokens is not None:
            change |= {
                "tokens_cache_read": tokens.input_cache_read,
                "tokens_uncached": tokens.input_uncached,
                "tokens_output": tokens.output,
            }
        return await self._finalize(run_id, **change)

    async def wait_approval(self, run_id: str, *, tokens: TokenUsage) -> bool:
        """把 run 挂到「等人确认」上，并记下到此为止的用量。

        **不是终态**，但走的是同一句条件更新：教师在最后一刻点了停止时，
        `cancelled` 已经写下，这里就不该再把它拉回 `waiting_approval`。

        Args:
            run_id: 目标 run。
            tokens: 到中断为止已经消耗的用量。

        Returns:
            这一次调用是否真的改变了状态。
        """
        return await self._transit(
            run_id,
            status=RunStatus.WAITING_APPROVAL,
            tokens_cache_read=tokens.input_cache_read,
            tokens_uncached=tokens.input_uncached,
            tokens_output=tokens.output,
        )

    async def resume(self, run_id: str) -> bool:
        """审批之后重新排队。

        **只有 `waiting_approval` 的 run 能被恢复** —— 教师在审批期间点了停止，
        或者审批超时转了 `cancelled`，这一句就该什么都不做。

        Args:
            run_id: 目标 run。

        Returns:
            这一次调用是否真的改变了状态。
        """
        identifier = _parse(run_id)
        if identifier is None:
            return False
        statement = (
            update(RunRecord)
            .where(col(RunRecord.id) == identifier, col(RunRecord.status) == RunStatus.WAITING_APPROVAL)
            .values(status=RunStatus.QUEUED, ended_at=None)
        )
        async with AsyncSession(self._engine) as session:
            result = await session.exec(statement)
            await session.commit()
        return bool(result.rowcount)

    async def _finalize(self, run_id: str, **change: object) -> bool:
        """写一次终态，顺手盖上结束时间。见 `_transit`。"""
        return await self._transit(run_id, ended_at=datetime.now(UTC), **change)

    async def _transit(self, run_id: str, **change: object) -> bool:
        """改一次状态，**只在这个 run 还没走到终态时才改**。

        条件写在 SQL 的 WHERE 里，因此这一句是原子的 —— 谁改成了谁负责推事件，
        另一边拿到 False 就安静退出。这一点有几个非它不可的场合：

        - 教师在最后一刻点了停止：api 已经写下 `cancelled` 并推过事件，而 worker 那一侧
          正好跑完。无条件写的话它会把状态盖回 `succeeded`，于是事件说已取消、
          状态说已成功，两边对不上而且谁都不报错；
        - 教师连点两下停止：无条件写会推出两条「已取消」；
        - 教师在审批期间点了停止：无条件写会把 `cancelled` 拉回 `waiting_approval`。

        Returns:
            这一次调用是否真的改变了状态。
        """
        identifier = _parse(run_id)
        if identifier is None:
            logger.warning("run id 不是合法 uuid，状态未落库：run_id=%s", run_id)
            return False
        statement = (
            update(RunRecord)
            .where(col(RunRecord.id) == identifier, col(RunRecord.status).in_(CANCELLABLE_STATUS))
            .values(**change)
        )
        async with AsyncSession(self._engine) as session:
            result = await session.exec(statement)
            await session.commit()
        return bool(result.rowcount)

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
