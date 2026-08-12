"""待审批的堆积与超时。

超时清扫是 cron 任务，与 `store.retention` 同一个形态：

    cd app && uv run python -m run.approval

**决策的形状与校验不在这里**，在 `run/decision.py` —— 那些要随任务消息走到 worker，
而任务消息的定义被配置层引用，放在一起会兜出一个循环导入。
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from config import StoreSettings
from event.model import Event, RunCancelledData, RunCancelledEvent, RunStatus, now_ms
from log import configure
from run.archive import EventArchive
from run.log import EventLog, LoggedEvent
from run.repository import RunRecord, RunRepository
from store import postgres, redis

logger = logging.getLogger(__name__)

# 等人确认最多挂多久。教师可能下班后才看到，几小时太短；但也不能永久挂着 ——
# 一个永远等下去的 run 会一直占着待审批名额
DEFAULT_TIMEOUT_HOUR = 24

# 一个用户最多能同时挂着几个待审批。**它与并发配额是两回事**：
# 那道闸管的是资源占用（waiting_approval 既不占 worker 也不占沙箱，因此不占并发），
# 这道闸管的是堆积。用同一个配额同时管两者会让其中一个失效
DEFAULT_PENDING_LIMIT = 5


class EventLogProtocol(Protocol):
    """超时清扫对事件日志的全部要求：只有追加。"""

    async def append(self, event: Event) -> LoggedEvent:
        """追加一条事件。"""
        ...


async def pending_count(engine: AsyncEngine, user_id: str) -> int:
    """这个用户手里挂着几个待审批。

    Args:
        engine: 到 Postgres 的异步引擎。
        user_id: 用户标识。

    Returns:
        状态为 `waiting_approval` 的行数；id 不合法时按 0 算。
    """
    try:
        owner = UUID(user_id)
    except ValueError:
        return 0

    async with AsyncSession(engine) as session:
        found = await session.exec(
            select(func.count())
            .select_from(RunRecord)
            .where(col(RunRecord.user_id) == owner, col(RunRecord.status) == RunStatus.WAITING_APPROVAL)
        )
        return int(found.one())


async def expired(
    engine: AsyncEngine, *, now: datetime | None = None, timeout_hour: int = DEFAULT_TIMEOUT_HOUR
) -> list[str]:
    """列出挂太久、该转 `cancelled` 的 run。

    **判据是 `started_at` 而不是「进入 waiting_approval 的时刻」** —— 后者没有单独的
    列，而一个 run 从提交到中断只隔几分钟，两者的差别远小于 24 小时这个量级。

    Args:
        engine: 到 Postgres 的异步引擎。
        now: 当前时刻。
        timeout_hour: 超时时长，小时。

    Returns:
        超时的 run id。
    """
    cutoff = (now or datetime.now(UTC)) - timedelta(hours=timeout_hour)
    async with AsyncSession(engine) as session:
        found = await session.exec(
            select(RunRecord).where(
                col(RunRecord.status) == RunStatus.WAITING_APPROVAL,
                col(RunRecord.started_at) < cutoff,
            )
        )
        return [record.id.hex for record in found.all()]


async def sweep(
    engine: AsyncEngine,
    log: EventLogProtocol,
    *,
    now: datetime | None = None,
    timeout_hour: int = DEFAULT_TIMEOUT_HOUR,
) -> int:
    """把挂太久的待审批转成 `cancelled` 并推事件。

    **这是 cron 任务的那一半**，与 `store.retention` 同一个形态：跑一次清一批，
    跑完退出，随时可以重跑 —— 条件更新保证第二次什么都不会发生。

    Args:
        engine: 到 Postgres 的异步引擎。
        log: 事件日志，用来推 `run.cancelled`。
        now: 当前时刻。
        timeout_hour: 超时时长，小时。

    Returns:
        这一次转掉了几个。
    """
    repository = RunRepository(engine)
    swept = 0
    for run_id in await expired(engine, now=now, timeout_hour=timeout_hour):
        # **条件更新**：教师可能刚好在这一刻点了确认或停止，那时这里就该什么都不做
        if not await repository.cancel(run_id):
            continue
        await log.append(RunCancelledEvent(ts=now_ms(), run_id=run_id, path=(), data=RunCancelledData()))
        logger.info("待审批超过 %d 小时，已转取消：run_id=%s", timeout_hour, run_id)
        swept += 1
    return swept


async def _main() -> None:
    settings = StoreSettings()
    engine = postgres.create_engine(settings.postgres_dsn())
    await postgres.check(engine)
    cache = redis.create_client(settings.redis_url)
    await redis.check(cache)
    try:
        removed = await sweep(engine, EventLog(cache, archive=EventArchive(engine)))
        logger.info("待审批超时清扫完成：转取消 %d 个", removed)
    finally:
        await engine.dispose()
        await cache.aclose()


def main() -> None:
    """进程入口。"""
    configure()
    asyncio.run(_main())


if __name__ == "__main__":
    main()
