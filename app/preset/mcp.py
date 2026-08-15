"""MCP 目录的读写：一条目录记录就是一台校外机器的地址与它的四项声明。

**这张表与 `agents` / `skills` 有一处结构性差别：没有版本序列。** 那两张表能冻结
版本，是因为内容在平台手里 —— 提示词是库里的一行，skill 是宿主机上的字节。MCP 的
内容在校外那台机器上，平台存的只是一个地址与一份「上架时它长这样」的记录。**引用
因此只冻结 `{server_id, name}`，冻不住行为**：翻一条三个月前的历史 run，看得出它用了
哪个服务，看不出那次调用拿到了什么 —— 那要去事件流里读 `tool_result`。

**凭据不进这张表。** 库里只存键名，值在 `.env` 里 —— 于是「谁能读库」与「谁能读凭据」
是两件事，而这张表要被前端读（目录卡片）。

**状态是一条链，不是一个开关**：`pending`（教师提了申请）→ `enabled`（管理员放行，
全平台可勾）或 `rejected`（管理员拒了）；`enabled` 之后还能因管理员手动停用或连续
失败熔断转 `disabled`，`disabled_reason` 记下是哪一种。
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import Index, text, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import Column, Field, SQLModel, col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from preset.model import _value_enum

TABLE_NAME = "mcp_servers"

MCP_NAME_INDEX = "ux_mcp_servers_name"

# 重名只在**没被拒**的那些之间算数。全表唯一的话，一次被拒的申请会把那个名字永久占住
MCP_NAME_CONDITION = "status <> 'rejected'"

logger = logging.getLogger(__name__)


class McpTransport(StrEnum):
    """允许的传输方式。

    **`stdio` 不在这里，而且不是靠校验挡住的。** 一个 stdio 型 MCP 等于在 worker
    容器里 `fork/exec`，那是任意代码执行 —— 枚举里根本没有这个值，写不进库。
    """

    STREAMABLE_HTTP = "streamable_http"
    SSE = "sse"


class McpStatus(StrEnum):
    """一条目录记录走到哪一步了。"""

    PENDING = "pending"
    ENABLED = "enabled"
    DISABLED = "disabled"
    REJECTED = "rejected"


class McpServerRecord(SQLModel, table=True):
    """`mcp_servers` 表的一行：一台校外机器的地址、它的四项声明与当前状态。

    四项声明依次是接入规范形式 C 的第 5～8 项：`tool_names`（接口描述）、
    `latency_note`（耗时）、`stores_user_data` 与 `sends_data_out`（数据）、
    `has_write_operation`（写操作）。**最后一项是硬闸门**：声明有写操作的批不了。
    """

    __tablename__ = TABLE_NAME
    __table_args__ = (Index(MCP_NAME_INDEX, "name", unique=True, postgresql_where=text(MCP_NAME_CONDITION)),)

    id: UUID = Field(primary_key=True)
    name: str
    description: str = Field(default="")
    url: str
    transport: McpTransport = Field(sa_column=_value_enum(McpTransport))
    # **只存键名，值在 .env 的 MCP_CREDENTIALS 里。** 不设凭据的服务留空
    credential_key: str | None = Field(default=None)
    # 上架时它长这样。装配时拿实际工具名与这份比对，不一致记 WARNING ——
    # 清单过期是静默的，不比对就永远发现不了
    tool_names: list[str] = Field(default_factory=list, sa_column=Column(JSONB, nullable=False))
    latency_note: str = Field(default="")
    stores_user_data: bool = Field(default=False)
    sends_data_out: bool = Field(default=True)
    has_write_operation: bool = Field(default=False)
    status: McpStatus = Field(sa_column=_value_enum(McpStatus))
    # 停用原因。管理员手动停用与熔断自动停用都写这里，后台照它显示「已自动停用」
    disabled_reason: str | None = Field(default=None)
    submitted_by: UUID = Field(index=False, foreign_key="users.id")
    reviewed_by: UUID | None = Field(default=None, index=False, foreign_key="users.id")
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class McpServer:
    """一条目录记录，含四项声明与状态。**不含凭据值。**"""

    id: str
    name: str
    description: str
    url: str
    transport: McpTransport
    credential_key: str | None
    tool_names: list[str]
    latency_note: str
    stores_user_data: bool
    sends_data_out: bool
    has_write_operation: bool
    status: McpStatus
    disabled_reason: str | None
    submitted_by: str
    reviewed_by: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class McpApplication:
    """教师提交的一份申请。字段与四项声明一一对应。"""

    name: str
    description: str
    url: str
    transport: McpTransport
    credential_key: str | None
    tool_names: list[str]
    latency_note: str
    stores_user_data: bool
    sends_data_out: bool
    has_write_operation: bool


class McpRepository:
    """`mcp_servers` 表的读写。"""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def apply(self, application: McpApplication, *, submitted_by: str) -> McpServer | None:
        """建一条待审记录；重名时返回 None。"""
        submitter = _parse(submitted_by)
        if submitter is None:
            return None
        now = datetime.now(UTC)
        record = McpServerRecord(
            id=uuid4(),
            name=application.name,
            description=application.description,
            url=application.url,
            transport=application.transport,
            credential_key=application.credential_key,
            tool_names=list(application.tool_names),
            latency_note=application.latency_note,
            stores_user_data=application.stores_user_data,
            sends_data_out=application.sends_data_out,
            has_write_operation=application.has_write_operation,
            status=McpStatus.PENDING,
            submitted_by=submitter,
            created_at=now,
            updated_at=now,
        )
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            session.add(record)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                return None
        logger.info("MCP 申请：server_id=%s name=%s by=%s", record.id.hex, record.name, submitted_by)
        return _to_server(record)

    async def get(self, server_id: str) -> McpServer | None:
        """按标识读一条记录，不看状态。"""
        identifier = _parse(server_id)
        if identifier is None:
            return None
        async with AsyncSession(self._engine) as session:
            record = await session.get(McpServerRecord, identifier)
        return None if record is None else _to_server(record)

    async def list_catalog(self) -> list[McpServer]:
        """教师看得见的目录：**只有放行了的**。

        被自动停用的也不在这里 —— 勾一个连不上的服务只会浪费一次装配。
        """
        return await self._list(col(McpServerRecord.status) == McpStatus.ENABLED)

    async def list_all(self) -> list[McpServer]:
        """管理员后台：待审、已上架、已停用、已拒全都要看得见。"""
        return await self._list(None)

    async def decide(self, server_id: str, *, reviewer_id: str, approved: bool, reason: str | None) -> bool:
        """放行或拒绝一条待审记录；已经处理过的返回 False。"""
        identifier, reviewer = _parse(server_id), _parse(reviewer_id)
        if identifier is None or reviewer is None:
            return False
        statement = (
            update(McpServerRecord)
            .where(
                col(McpServerRecord.id) == identifier,
                col(McpServerRecord.status) == McpStatus.PENDING,
            )
            .values(
                status=McpStatus.ENABLED if approved else McpStatus.REJECTED,
                disabled_reason=None if approved else reason,
                reviewed_by=reviewer,
                updated_at=datetime.now(UTC),
            )
            .returning(col(McpServerRecord.id))
        )
        async with self._engine.begin() as connection:
            changed = (await connection.execute(statement)).first()
        if changed is None:
            return False
        logger.info("MCP 审批：server_id=%s approved=%s by=%s", server_id, approved, reviewer_id)
        return True

    async def set_enabled(self, server_id: str, *, enabled: bool, reason: str | None) -> bool:
        """手动启停一条已放行的记录。

        **只在 `enabled` 与 `disabled` 之间来回**：待审的还没放行、被拒的没被放行过，
        对它们「启用」等于绕过审批。
        """
        identifier = _parse(server_id)
        if identifier is None:
            return False
        statement = (
            update(McpServerRecord)
            .where(
                col(McpServerRecord.id) == identifier,
                col(McpServerRecord.status).in_([McpStatus.ENABLED, McpStatus.DISABLED]),
            )
            .values(
                status=McpStatus.ENABLED if enabled else McpStatus.DISABLED,
                disabled_reason=None if enabled else reason,
                updated_at=datetime.now(UTC),
            )
            .returning(col(McpServerRecord.id))
        )
        async with self._engine.begin() as connection:
            changed = (await connection.execute(statement)).first()
        if changed is None:
            return False
        logger.info("MCP 启停：server_id=%s enabled=%s reason=%s", server_id, enabled, reason)
        return True

    async def disable_for_failure(self, server_id: str, *, reason: str) -> bool:
        """熔断到阈值时自动停用。

        **只对还在 `enabled` 的那些生效**，于是并发的两条失败路径只会写一次库。
        """
        identifier = _parse(server_id)
        if identifier is None:
            return False
        statement = (
            update(McpServerRecord)
            .where(
                col(McpServerRecord.id) == identifier,
                col(McpServerRecord.status) == McpStatus.ENABLED,
            )
            .values(status=McpStatus.DISABLED, disabled_reason=reason, updated_at=datetime.now(UTC))
            .returning(col(McpServerRecord.id))
        )
        async with self._engine.begin() as connection:
            changed = (await connection.execute(statement)).first()
        if changed is None:
            return False
        logger.warning("MCP 自动停用：server_id=%s reason=%s", server_id, reason)
        return True

    async def _list(self, condition: ColumnElement[bool] | None) -> list[McpServer]:
        statement = select(McpServerRecord).order_by(col(McpServerRecord.name))
        if condition is not None:
            statement = statement.where(condition)
        async with AsyncSession(self._engine) as session:
            found = await session.exec(statement)
            return [_to_server(one) for one in found.all()]


def _parse(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None


def _to_server(record: McpServerRecord) -> McpServer:
    return McpServer(
        id=record.id.hex,
        name=record.name,
        description=record.description,
        url=record.url,
        transport=record.transport,
        credential_key=record.credential_key,
        tool_names=list(record.tool_names),
        latency_note=record.latency_note,
        stores_user_data=record.stores_user_data,
        sends_data_out=record.sends_data_out,
        has_write_operation=record.has_write_operation,
        status=record.status,
        disabled_reason=record.disabled_reason,
        submitted_by=record.submitted_by.hex,
        reviewed_by=None if record.reviewed_by is None else record.reviewed_by.hex,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )
