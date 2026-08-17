"""run 元数据的落库：`runs` 表的结构与读写。

**这张表存在的理由是进程边界**。P1 之前 run 的状态是执行器内存里的一个 dict，
而 worker 拆出去之后那个 dict 在 worker 进程里，查询请求却打在 api 进程上 ——
`GET /runs/{id}` 会直接失效。落库之后两个进程看到的是同一份。

表结构由 Alembic 管（`migration/`），不在这里 `create_all` —— 两条路都能建表时，
它们迟早会分叉。
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Column, Enum, Index, func, text, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import Field, SQLModel, col, select, tuple_
from sqlmodel.ext.asyncio.session import AsyncSession

from app.agent.config import AgentConfig
from app.event.model import RunErrorCode, RunStatus, TokenUsage
from cursor import DEFAULT_PAGE_SIZE, Page, decode, encode, split

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

# 「这一程不是第一次开跑」的那几个前态。`queued` 不在里面 —— 那正是第一次的样子
RESUMABLE_STATUS = (RunStatus.RUNNING, RunStatus.WAITING_APPROVAL)

# 还活着的那几态。**与 `CANCELLABLE_STATUS` 眼下取值相同，但问的是两件事**：那边问
# 「还能不能改它的状态」，这边问「它还在占着资源吗」。合成一个常量的话，将来任何一边
# 变了都会悄悄改掉另一边的语义
LIVE_STATUS = (RunStatus.QUEUED, RunStatus.RUNNING, RunStatus.WAITING_APPROVAL)


class RunStart(StrEnum):
    """一次 `start()` 的性质。

    **`FIRST` 与 `RESUMED` 对前端的含义完全不同**：前者是新一轮分析开跑，后者是
    「接着刚才那一程」—— 把已经显示的对话重置掉是错的。
    """

    FIRST = "first"
    RESUMED = "resumed"
    # 已经有终态了，这一次投递不该执行
    REFUSED = "refused"


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

    只放执行状态与审批续跑必需的快照。翻看历史要的其余字段在 `RunDetail` ——
    分成两个形状是为了不让高频的状态查询携带用不到的历史字段。
    """

    id: str
    thread_id: str
    status: RunStatus
    agent_config: AgentConfig = field(default_factory=AgentConfig)


@dataclass(frozen=True)
class RunDetail:
    """会话历史里的一轮问答。

    **`content` 是聊天历史的用户那一侧。** 事件流里没有承载提问的事件，因此把一个 run
    的事件全部重放一遍，重建出来的对话只有 agent 那一半 —— 用户的问题气泡只能从这里来。
    """

    id: str
    thread_id: str
    status: RunStatus
    # 教师的问题。本版之前的 run 在这一列上是空的，那是遗留而不是待回填的空缺
    content: str | None
    tokens: TokenUsage
    error_code: RunErrorCode | None
    error_message: str | None
    started_at: datetime
    # 还没跑完的为空
    ended_at: datetime | None
    agent_config: AgentConfig = field(default_factory=AgentConfig)


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
    # 教师的问题。本版之前的 run 在这一列上是空的 —— 那些提问已经不存在于任何地方
    content: str | None = Field(default=None)
    # 这次 run 实际生效的配置快照。P6 之前的历史行为 NULL，读时当默认配置。
    agent_config: dict[str, object] | None = Field(default=None, sa_column=Column(JSONB, nullable=True))
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
        return Run(
            id=self.id.hex,
            thread_id=self.thread_id.hex,
            status=self.status,
            agent_config=AgentConfig.model_validate({} if self.agent_config is None else self.agent_config),
        )

    def to_detail(self) -> RunDetail:
        """转成会话历史里那个形状。"""
        return RunDetail(
            id=self.id.hex,
            thread_id=self.thread_id.hex,
            status=self.status,
            content=self.content,
            tokens=TokenUsage(
                input_cache_read=self.tokens_cache_read,
                input_uncached=self.tokens_uncached,
                output=self.tokens_output,
            ),
            error_code=self.error_code,
            error_message=self.error_message,
            started_at=self.started_at,
            ended_at=self.ended_at,
            agent_config=AgentConfig.model_validate({} if self.agent_config is None else self.agent_config),
        )


class RunRepository:
    """`runs` 表的读写。

    Args:
        engine: 到 Postgres 的异步引擎。
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def create(
        self,
        *,
        run_id: str,
        thread_id: str,
        user_id: str,
        content: str | None = None,
        agent_config: dict[str, object] | None = None,
    ) -> None:
        """记下一个刚提交、还没开跑的 run。

        `user_id` 是有意的反范式（严格范式下它该经 `threads` 推导）：配额统计与隔离
        过滤两条高频路径都要按用户聚合，每次都 join 不值得。一致性由这个唯一入口
        保证 —— 而调用方在提交之前已经用同一个 `user_id` 查过 thread，查不到就走不到这里。

        Args:
            run_id: run 标识。
            thread_id: 所属会话。
            user_id: 提交的人。
            content: 教师的问题。不给就是「没记下来」，与本版之前那批 run 同义 ——
                那样的 run 在会话历史里只有 agent 那一半。
            agent_config: 这次 run 实际生效的配置快照。
        """
        record = RunRecord(
            id=UUID(run_id),
            thread_id=UUID(thread_id),
            user_id=UUID(user_id),
            content=content,
            agent_config=agent_config,
            status=RunStatus.QUEUED,
            started_at=datetime.now(UTC),
        )
        async with AsyncSession(self._engine) as session:
            session.add(record)
            await session.commit()

    async def live_statuses(self, thread_ids: list[str], *, user_id: str) -> dict[str, RunStatus]:
        """一批会话各自「还在跑的 run」的状态，按会话聚合。

        会话列表要显示哪个会话正在进行中，而这个信息属于 `runs` 表 —— 这里按
        thread 批量查一次，列表页就不必一页发 N 条查询。终态不算「在跑」，
        缺席即不在结果里。同一个会话有多个在跑时取 `started_at` 最新的那个。

        **与其他公开方法一样要求 `user_id`**：隔离门禁（store/isolation_test）
        不允许任何不带用户上下文的入口 —— 少了它，别人 thread 的 run 状态也能
        被批量探测。
        """
        owner = _parse(user_id)
        ids = [one for one in (_parse(value) for value in thread_ids) if one is not None]
        if owner is None or not ids:
            return {}
        async with AsyncSession(self._engine) as session:
            found = await session.exec(
                select(RunRecord)
                .where(
                    col(RunRecord.thread_id).in_(ids),
                    col(RunRecord.user_id) == owner,
                    col(RunRecord.status).in_((RunStatus.QUEUED, RunStatus.RUNNING, RunStatus.WAITING_APPROVAL)),
                )
                .order_by(col(RunRecord.started_at).desc())
            )
        statuses: dict[str, RunStatus] = {}
        for record in found.all():
            # 按 started_at 倒序，第一次见到的就是最新的那一个
            statuses.setdefault(record.thread_id.hex, record.status)
        return statuses

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

    async def list_by_thread(
        self,
        thread_id: str,
        *,
        user_id: str,
        cursor: str | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
    ) -> Page[RunDetail]:
        """列出一个会话里的历次分析，**最近的在前**。

        这就是聊天历史：每一条给出教师问了什么与那一轮的结局，过程事件由
        `GET /runs/{id}/events` 逐个重放。

        **倒序而不是正序**：教师打开会话先看最近几轮，往上滚才翻更早的 ——
        与 `ix_runs_thread_started` 同向，第一页不必扫过整段历史。

        Args:
            thread_id: 会话标识。
            user_id: 当前用户。别人的会话给空列表，与不存在同一个结果。
            cursor: 上一页给的游标，不传则从最近的开始。
            limit: 一页几条。

        Returns:
            这一页问答，以及取下一页要带的游标。

        Raises:
            CursorError: 游标不合法。
        """
        thread, owner = _parse(thread_id), _parse(user_id)
        if thread is None or owner is None:
            return Page(items=[], next_cursor=None)

        statement = select(RunRecord).where(col(RunRecord.thread_id) == thread, col(RunRecord.user_id) == owner)
        if cursor is not None:
            statement = statement.where(tuple_(col(RunRecord.started_at), col(RunRecord.id)) < decode(cursor))

        async with AsyncSession(self._engine) as session:
            found = await session.exec(
                statement.order_by(col(RunRecord.started_at).desc(), col(RunRecord.id).desc()).limit(limit + 1)
            )
            page, has_more = split(list(found.all()), limit)

        return Page(
            items=[one.to_detail() for one in page],
            next_cursor=encode(page[-1].started_at, page[-1].id) if has_more else None,
        )

    async def start(self, run_id: str) -> RunStart:
        """标记开跑，并回答**这是不是第一次开跑**。

        **同样是条件更新**：一条已经取消的 run 若因为消息重投又被领走，
        无条件写会把它从 `cancelled` 拉回 `running`，于是一次已经取消的分析
        又跑了起来 —— 而状态与事件从此对不上。

        **拆成两步而不是一句 `IN (...)`**：先试 `queued → running`，命中就是第一次；
        没命中再试 `running / waiting_approval → running`，命中就是重投接着跑。
        一句话写不出这个区别 —— 它要的是「命中的是哪个前态」，而 `UPDATE` 只回答
        「改了几行」。两步各自原子，中间那一刻状态再变也只会让第二步落空而已。

        Returns:
            这一次开跑的性质。
        """
        if await self._transit_from(run_id, (RunStatus.QUEUED,), status=RunStatus.RUNNING):
            return RunStart.FIRST
        if await self._transit_from(run_id, RESUMABLE_STATUS, status=RunStatus.RUNNING):
            return RunStart.RESUMED
        return RunStart.REFUSED

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

    async def _transit_from(self, run_id: str, allowed: tuple[RunStatus, ...], **change: object) -> bool:
        """改一次状态，**只在当前状态落在给定集合里时才改**。见 `_transit`，那是它的全集版本。"""
        identifier = _parse(run_id)
        if identifier is None:
            logger.warning("run id 不是合法 uuid，状态未落库：run_id=%s", run_id)
            return False
        statement = (
            update(RunRecord)
            .where(col(RunRecord.id) == identifier, col(RunRecord.status).in_(allowed))
            .values(**change)
        )
        async with AsyncSession(self._engine) as session:
            result = await session.exec(statement)
            await session.commit()
        return bool(result.rowcount)

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
        return await self._transit_from(run_id, CANCELLABLE_STATUS, **change)

    async def unfinished(self, *, started_before: datetime | None = None) -> list[Run]:
        """列出还没走到终态的 run。

        **这是本类里唯一不带 user 上下文的查询**，因为它不服务任何用户请求：
        扫的是「此刻还没跑完的 run」，调用方是收割孤儿的 cron，
        那里根本没有登录用户。走 `ix_runs_unfinished` 那条部分索引。

        Args:
            started_before: 只要早于这个时刻提交的。收割器用它留一段宽限期 ——
                那一段挡的是「先读库、再读队列」这两步之间的时间差：一个 run 若
                恰好在这中间才被投进队列，库里已经有行而队列里还没有它，
                不留宽限期就会把一次刚提交的分析当场判成孤儿。不给就是全量。

        Returns:
            状态为 `queued` 或 `running` 的 run，按提交顺序。
        """
        statement = select(RunRecord).where(col(RunRecord.status).in_(UNFINISHED_STATUS))
        if started_before is not None:
            statement = statement.where(col(RunRecord.started_at) < started_before)
        async with AsyncSession(self._engine) as session:
            found = await session.exec(statement.order_by(col(RunRecord.started_at)))
            return [record.to_run() for record in found.all()]

    async def live_count(self) -> dict[RunStatus, int]:
        """按状态数一遍还没走到终态的 run。

        **只数活着的那几态。** 终态的累计数不在这里 —— 那是看板的活，做成指标只会得到
        一条永远在涨的线。也正因为只数活的，这条查询的结果集永远是很小的一撮。

        Returns:
            `状态 → 个数`。一个都没有的状态不出现在结果里。
        """
        async with AsyncSession(self._engine) as session:
            statement = (
                select(col(RunRecord.status), func.count())
                .where(col(RunRecord.status).in_(LIVE_STATUS))
                .group_by(col(RunRecord.status))
            )
            found = await session.exec(statement)
            return {status: count for status, count in found.all()}

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
