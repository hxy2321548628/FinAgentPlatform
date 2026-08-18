"""孤儿 run 的收割：库里还活着、队列里却已经没有它了。

清扫是 cron 任务，与 `store.retention`、`run.approval` 同一个形态：

    cd src && uv run python -m app.run.reaper

**为什么需要它。** worker 的 ack 写在主循环的 `finally` 里，无条件执行；而执行器
起跑阶段有几处调用落在它自己那圈 `try/except` 之外（读取消标志、写 `start()`、
推 `run.started`）。这几处任何一处抛 —— Redis 抖一下、Postgres 连接断一下 ——
异常冒到主循环，那里记一笔日志然后照样 ack。于是这个 run 既不在队列的 pending
列表里，状态又停在 `queued` 或 `running`：**此后没有任何东西会再碰它**。
教师看到的是一个永远转圈的分析，不报错、不超时、不消失。

**为什么不是重投。** 重投就是自动重试，而这个项目明确不做（见 `run/executor.py`
的模块 docstring：「重不重试由人决定」）。更硬的理由是并发：这个进程与 worker 各跑各的，
重投一条 worker 其实还认领得回来的消息，第二份的 `start()` 会撞上 `running → running`
拿到 `RESUMED` 而照跑不误 —— 同一个 run 并发跑两遍，共用一个沙箱、写同一份
checkpoint。收割成 `failed` 且 `retryable=True`，把决定权交回给人，两个问题一起没有。

**判据只有一条：队列里还有没有它。** 不能用「跑了多久」代替 —— 一次分析本来就可能
跑几十分钟，而队列的 pending 列表里有健康 worker 每 15 秒续的命，那才是活着的证据。
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Protocol

from app.event.model import Event, RunErrorCode, RunFailedData, RunFailedEvent, now_ms
from app.run.archive import EventArchive
from app.run.log import EventLog, LoggedEvent
from app.run.repository import Run, RunRepository
from app.store import postgres, redis
from app.task.queue import TaskQueue
from config import StoreSettings
from log import configure

logger = logging.getLogger(__name__)

# 刚提交的 run 留多久不碰。**这一段挡的是两次读之间的时间差**：收割器先读库再读队列，
# 一个 run 若恰好在这中间才被投进队列，库里已经有行而队列里还没有它。
# 十分钟远大于那个间隔，又远小于「教师会开始觉得不对劲」的时长
DEFAULT_GRACE_MINUTE = 10

CONSUMER_NAME = "reaper"

ORPHAN_MESSAGE = "这次分析中断了：执行它的进程没有留下结果，任务也已不在队列里。可以重新提交。"


class RunSourceProtocol(Protocol):
    """收割器对 run 仓储的全部要求：查还活着的，和把其中一个判失败。"""

    async def unfinished(self, *, started_before: datetime | None = None) -> list[Run]:
        """列出还没走到终态的 run。"""
        ...

    async def fail(self, run_id: str, *, code: RunErrorCode, message: str) -> bool:
        """标记失败，并回答这一次是不是自己写下的终态。"""
        ...


class QueueProtocol(Protocol):
    """收割器对队列的全部要求：只问「还有谁在里面」。"""

    async def in_flight(self) -> set[str]:
        """队列里还没跑完的那些 run。"""
        ...


class EventLogProtocol(Protocol):
    """收割器对事件日志的全部要求：只有追加。"""

    async def append(self, event: Event) -> LoggedEvent:
        """追加一条事件。"""
        ...


async def orphaned(
    repository: RunSourceProtocol,
    queue: QueueProtocol,
    *,
    now: datetime | None = None,
    grace_minute: int = DEFAULT_GRACE_MINUTE,
) -> list[str]:
    """列出没有任何东西会再碰的 run。

    **先读库再读队列，顺序是有讲究的**：反过来的话，一个在两次读之间才提交的 run
    会先不在队列快照里、后出现在库里，于是被当场判成孤儿。按这个顺序，
    那样的 run 只会落在「库里没有、队列里有」这一侧，而那一侧不产生任何动作。
    宽限期再兜一层。

    Args:
        repository: run 元数据的仓储。
        queue: 任务队列。
        now: 当前时刻。
        grace_minute: 刚提交的 run 留多久不碰。

    Returns:
        该收割的 run id。
    """
    cutoff = (now or datetime.now(UTC)) - timedelta(minutes=grace_minute)
    live = await repository.unfinished(started_before=cutoff)
    if not live:
        return []
    in_flight = await queue.in_flight()
    return [one.id for one in live if one.id not in in_flight]


async def sweep(
    repository: RunSourceProtocol,
    queue: QueueProtocol,
    log: EventLogProtocol,
    *,
    now: datetime | None = None,
    grace_minute: int = DEFAULT_GRACE_MINUTE,
) -> int:
    """把孤儿 run 判成失败并推事件。

    **跑一次清一批，跑完退出，随时可以重跑** —— 第二次什么都不会发生，
    靠的是 `fail()` 的条件更新而不是记账。

    Args:
        repository: run 元数据的仓储。
        queue: 任务队列。
        log: 事件日志，用来推 `run.failed`。
        now: 当前时刻。
        grace_minute: 刚提交的 run 留多久不碰。

    Returns:
        这一次收割了几个。
    """
    reaped = 0
    for run_id in await orphaned(repository, queue, now=now, grace_minute=grace_minute):
        # **条件更新**：读到它还活着、动手之前它跑完了 —— 那一刻推 `run.failed`
        # 会把一次成功的分析显示成失败
        if not await repository.fail(run_id, code=RunErrorCode.ORPHANED, message=ORPHAN_MESSAGE):
            continue
        await log.append(
            RunFailedEvent(
                ts=now_ms(),
                run_id=run_id,
                path=(),
                data=RunFailedData(code=RunErrorCode.ORPHANED, message=ORPHAN_MESSAGE, retryable=True),
            )
        )
        logger.info("run 已不在队列里，判为中断：run_id=%s", run_id)
        reaped += 1
    return reaped


async def _main() -> None:
    settings = StoreSettings()
    engine = postgres.create_engine(settings.postgres_dsn())
    await postgres.check(engine)
    cache = redis.create_client(settings.redis_url)
    await redis.check(cache)
    try:
        reaped = await sweep(
            RunRepository(engine),
            # **消费者名单独取一个**：收割器只读不领，但 `TaskQueue` 的构造要一个名字，
            # 顶着某个 worker 的名字会让 `XINFO CONSUMERS` 里凭空多出一行
            TaskQueue(cache, consumer=CONSUMER_NAME),
            EventLog(cache, archive=EventArchive(engine)),
        )
        logger.info("孤儿 run 清扫完成：判为中断 %d 个", reaped)
    finally:
        await engine.dispose()
        await cache.aclose()


def main() -> None:
    """进程入口。"""
    configure()
    asyncio.run(_main())


if __name__ == "__main__":
    main()
