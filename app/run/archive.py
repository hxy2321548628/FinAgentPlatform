"""事件归档：Redis Stream 里的事件同时落一份到 `run_events`。

**Stream 是热数据，Postgres 是历史。** Stream 有条数上限也有 TTL，超出的部分会被裁掉；
教师翻几个月前的会话时，读的是这张表。

**写入是同步的双写，不是异步追赶。** 计划原本写的是「异步归档」，但异步意味着
「裁剪与归档之间有一个时间窗」，而那个窗口里被裁掉的事件会变成一段**不报错的空白**。
同步双写把这个窗口变成零。代价是每条事件多一次 INSERT（一次完整分析约 300 条，
实测每条零点几毫秒），换来的是不必去论证「一般来得及」。

**归档失败不打断 run**：教师拿到的分析结果仍然是对的，只是这一段历史以后翻不到。
失败要吼出来（ERROR），但不能把一次跑了半小时的分析掀掉 —— 而且事件还在 Stream 里，
补归档来得及。
"""

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import BigInteger, Column, Index
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import Field, SQLModel, col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from event.model import EVENT_ADAPTER, Event
from run.log import LoggedEvent, parse_event_id

logger = logging.getLogger(__name__)

TABLE_NAME = "run_events"

# 事件 id 是 `{毫秒}-{同毫秒内序号}`，而表的主键是一个 bigint（架构 §6.2 的草案）。
# 把两段打包进一个整数，既保住排序又能原样还原 id。
#
# 20 位给序号 = 一毫秒内一百万条，Redis 实际发不到这个量级；
# 上界则是 2^63 / 2^20 ≈ 8.8e12 毫秒，够用到公元 2248 年。
SEQUENCE_BIT = 20
SEQUENCE_MASK = (1 << SEQUENCE_BIT) - 1


def pack(event_id: str) -> int:
    """把事件 id 打包成一个可排序的整数。

    Args:
        event_id: 形如 `1753948800123-0` 的事件 id。

    Returns:
        `毫秒 << 20 | 序号`。

    Raises:
        InvalidEventIdError: 格式不合法。
    """
    millisecond, sequence = parse_event_id(event_id)
    return (millisecond << SEQUENCE_BIT) | sequence


def unpack(seq: int) -> str:
    """把打包过的整数还原成事件 id。"""
    return f"{seq >> SEQUENCE_BIT}-{seq & SEQUENCE_MASK}"


class RunEventRecord(SQLModel, table=True):
    """`run_events` 表的一行。"""

    __tablename__ = TABLE_NAME
    __table_args__ = (Index("ix_run_events_ts", "ts"),)

    run_id: UUID = Field(primary_key=True)
    # bigint 而不是默认的 integer：打包过的 id 早就超过 2^31 了
    seq: int = Field(sa_column=Column("seq", BigInteger, primary_key=True))
    type: str
    # 整个信封原样存下来，重放时不必再拼一遍 —— 拼的过程一旦与当初写入的不一致，
    # 前端拿到的就是一份「像是那次执行」的历史
    payload: dict[str, object] = Field(sa_column=Column("payload", JSONB, nullable=False))
    ts: datetime


class EventArchive:
    """`run_events` 表的读写。

    Args:
        engine: 到 Postgres 的异步引擎。
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def record(self, logged: LoggedEvent) -> None:
        """把一条已经写进 Stream 的事件落一份到表里。

        **重复写入是安全的**：主键冲突直接忽略。补归档、重投的 run 都会撞上这条。
        """
        identifier = _parse(logged.event.run_id)
        if identifier is None:
            logger.error("run id 不是合法 uuid，事件未归档：run_id=%s", logged.event.run_id)
            return
        statement = (
            insert(RunEventRecord)
            .values(
                run_id=identifier,
                seq=pack(logged.id),
                type=logged.event.type.value,
                payload=logged.event.model_dump(mode="json"),
                ts=datetime.fromtimestamp(logged.event.ts / 1000, tz=UTC),
            )
            .on_conflict_do_nothing(index_elements=["run_id", "seq"])
        )
        try:
            async with AsyncSession(self._engine) as session:
                await session.exec(statement)
                await session.commit()
        except SQLAlchemyError:
            logger.error("事件归档失败，这段历史将来翻不到：run_id=%s", logged.event.run_id, exc_info=True)

    async def replay(self, run_id: str, *, after: str | None = None, before: str | None = None) -> list[LoggedEvent]:
        """从表里读回一段事件。

        Args:
            run_id: 目标 run。
            after: 只要这个 id **之后**的；不传则从头。
            before: 只要这个 id **之前**的；不传则到尾。调用方用它避开 Stream 里已有的那段。

        Returns:
            按发生顺序排列的事件，没有则为空。
        """
        identifier = _parse(run_id)
        if identifier is None:
            return []
        statement = select(RunEventRecord).where(col(RunEventRecord.run_id) == identifier)
        if after is not None:
            statement = statement.where(col(RunEventRecord.seq) > pack(after))
        if before is not None:
            statement = statement.where(col(RunEventRecord.seq) < pack(before))
        statement = statement.order_by(col(RunEventRecord.seq))

        async with AsyncSession(self._engine) as session:
            found = await session.exec(statement)
            return [_decode(record) for record in found.all()]

    async def last(self, run_id: str) -> LoggedEvent | None:
        """一个 run 归档里的最后一条事件，没有则 None。

        Stream 整条过期之后，「这个 run 结束了没有」只能问它。
        """
        identifier = _parse(run_id)
        if identifier is None:
            return None
        statement = (
            select(RunEventRecord)
            .where(col(RunEventRecord.run_id) == identifier)
            .order_by(col(RunEventRecord.seq).desc())
            .limit(1)
        )
        async with AsyncSession(self._engine) as session:
            found = await session.exec(statement)
            record = found.first()
            return None if record is None else _decode(record)


def _decode(record: RunEventRecord) -> LoggedEvent:
    event: Event = EVENT_ADAPTER.validate_python(record.payload)
    return LoggedEvent(id=unpack(record.seq), event=event)


def _parse(run_id: str) -> UUID | None:
    """Run id 来自 URL，属于不可信输入 —— 解析不了就是「查不到」，不是 500。"""
    try:
        return UUID(run_id)
    except ValueError:
        return None
