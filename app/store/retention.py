"""保留期清理：把过了保留期的事件与 checkpoint 删掉。

    cd app && uv run python -m store.retention

**这是 cron 任务，不是常驻进程。** 跑一次删一批，跑完就退出；**随时可以重跑**，
删的是「早于某个时点」的行，重跑一次不会多删也不会少删。

关闭了[架构 §6.5](../../doc/01design/01architecture.md) 的两问之一：保留期。
另一问（备份频率与份数）是运维项，不在代码里。

**`runs` 那张表不清**：它是历史的索引，一行几十字节，教师需要「三个月前我问过什么」
这个列表 —— 清掉它等于把目录烧了只留正文。清的是正文：事件与 checkpoint。
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel.ext.asyncio.session import AsyncSession

from config import StoreSettings
from log import configure
from store import postgres

logger = logging.getLogger(__name__)

# 事件归档留多久。教师翻半年前的分析是合理需求，再往前就没人看了；
# 而这是全库最大的一张表，无限留会让备份先扛不住
DEFAULT_EVENT_RETENTION_DAY = 180

# 会话 checkpoint 留多久。**判据是会话最后一次活动，不是 checkpoint 自己的时间** ——
# LangGraph 的表里没有时间列，只能靠 runs 反推
DEFAULT_CHECKPOINT_RETENTION_DAY = 180

# 每条 DELETE 的批量上限。一次删几百万行会把表锁住，也会让 WAL 暴涨
DEFAULT_BATCH = 10_000

# checkpointer 自建的三张表。**只删行，不动结构** —— 结构随 LangGraph 版本走
CHECKPOINT_TABLE = ("checkpoint_writes", "checkpoint_blobs", "checkpoints")

DELETE_EVENT_SQL = """
DELETE FROM run_events
WHERE ctid IN (SELECT ctid FROM run_events WHERE ts < :cutoff LIMIT :batch)
"""

# 早于时点、且这个会话之后再没跑过东西的 thread。用 runs 反推是唯一的判据 ——
# 只看某一次 run 老会把还在用的会话的历史删掉。
#
# **要去掉横杠**：平台各处的 thread_id 都是 `uuid4().hex`（无横杠），checkpointer
# 的表里存的就是那个字符串；而 `runs.thread_id` 是 uuid 列，转成文本会带上横杠。
# 不去掉的话这条 SQL 一条也匹配不上 —— 而它不报错，只是一个 checkpoint 都清不掉
STALE_THREAD_SQL = """
SELECT replace(thread_id::text, '-', '') FROM runs GROUP BY thread_id HAVING max(started_at) < :cutoff
"""


async def purge_event(engine: AsyncEngine, *, cutoff: datetime, batch: int = DEFAULT_BATCH) -> int:
    """删掉早于 `cutoff` 的事件归档。

    Args:
        engine: 到 Postgres 的异步引擎。
        cutoff: 时点，早于它的都删。
        batch: 单批上限，分批删到没有为止。

    Returns:
        删掉的行数。
    """
    removed = 0
    async with AsyncSession(engine) as session:
        while True:
            result = await session.exec(text(DELETE_EVENT_SQL), params={"cutoff": cutoff, "batch": batch})  # type: ignore[call-overload]
            await session.commit()
            if not result.rowcount:
                return removed
            removed += result.rowcount


async def purge_checkpoint(engine: AsyncEngine, *, cutoff: datetime) -> int:
    """删掉早于 `cutoff` 就没再活动过的会话的 checkpoint。

    Args:
        engine: 到 Postgres 的异步引擎。
        cutoff: 时点，最后一次 run 早于它的会话都清。

    Returns:
        清掉的会话数。
    """
    async with AsyncSession(engine) as session:
        found = await session.exec(text(STALE_THREAD_SQL), params={"cutoff": cutoff})  # type: ignore[call-overload]
        stale = [row[0] for row in found]
        if not stale:
            return 0
        for table in CHECKPOINT_TABLE:
            await session.exec(  # type: ignore[call-overload]
                text(f"DELETE FROM {table} WHERE thread_id = ANY(:thread)"),
                params={"thread": stale},
            )
        await session.commit()
        return len(stale)


async def purge(
    engine: AsyncEngine,
    *,
    now: datetime,
    event_retention_day: int = DEFAULT_EVENT_RETENTION_DAY,
    checkpoint_retention_day: int = DEFAULT_CHECKPOINT_RETENTION_DAY,
) -> tuple[int, int]:
    """跑一遍清理。

    Args:
        engine: 到 Postgres 的异步引擎。
        now: 当前时刻，注入进来是为了让测试能把时钟拨过去。
        event_retention_day: 事件归档保留天数。
        checkpoint_retention_day: 会话 checkpoint 保留天数。

    Returns:
        (删掉的事件行数, 清掉的会话数)。
    """
    event = await purge_event(engine, cutoff=now - timedelta(days=event_retention_day))
    checkpoint = await purge_checkpoint(engine, cutoff=now - timedelta(days=checkpoint_retention_day))
    logger.info("保留期清理完成：删除事件 %d 行，清理会话 checkpoint %d 个", event, checkpoint)
    return event, checkpoint


async def _main() -> None:
    settings = StoreSettings()
    engine = postgres.create_engine(settings.postgres_dsn())
    await postgres.check(engine)
    try:
        await purge(engine, now=datetime.now(UTC))
    finally:
        await engine.dispose()


def main() -> None:
    """进程入口。"""
    configure()
    asyncio.run(_main())


if __name__ == "__main__":
    main()
