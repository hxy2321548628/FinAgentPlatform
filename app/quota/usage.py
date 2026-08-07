"""用量统计：一个用户今天烧了多少 token、此刻占着几个 run。

两个数都从 `runs` 表算，走 `ix_runs_user_started` 那条索引。**不另起一份 Redis 计数器**：
那样会有两个真相源，而它们分叉的方式是静默的 —— 计数器丢一次，闸门就永远松着。

**token 按未命中部分算，`cache_read` 一律不计入。** 实测 62% 的 input 是 cache 命中，
按 input 总数扣会高估约 1.6 倍，而且**方向性地惩罚长会话** —— 会话越长命中率越高、
边际成本越低，按总数扣却扣得越狠。而长会话深度分析正是平台想鼓励的。
扣错方向比扣错数值严重得多。
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from event.model import RunStatus
from run.repository import RunRecord

# 占着并发名额的状态。**`waiting_approval` 不在其中**（等步骤五落地）：
# 并发配额限制的是资源占用，而等人确认期间既不占 worker 也不占沙箱 ——
# 若把它算进来，教师忘了点确认就会把自己的配额锁死一整天
ACTIVE_STATUS = (RunStatus.QUEUED, RunStatus.RUNNING)


def day_start(now: datetime) -> datetime:
    """当天的起点。

    配额每日 0 点重置 —— 这与 `QUOTA_EXCEEDED` 的提示语「明日 0 点重置」是同一件事，
    两处不能各说各的。

    Args:
        now: 当前时刻。

    Returns:
        同一天的零点。
    """
    return now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


class RunUsage:
    """按用户统计 `runs` 表里的用量。

    Args:
        engine: 到 Postgres 的异步引擎。
        output_weight: output token 折算成当量的权重。
    """

    def __init__(self, engine: AsyncEngine, *, output_weight: int = 1) -> None:
        self._engine = engine
        self._output_weight = output_weight

    async def token_today(self, user_id: str, *, now: datetime | None = None) -> int:
        """这个用户今天已经烧掉的 token 当量。

        Args:
            user_id: 用户标识。
            now: 当前时刻，测试用它把「今天」挪到别处。

        Returns:
            未命中 input 加上加权后的 output；用户 id 不合法时按 0 算。
        """
        owner = _parse(user_id)
        if owner is None:
            return 0
        since = day_start(now or datetime.now(UTC))
        equivalent = col(RunRecord.tokens_uncached) + col(RunRecord.tokens_output) * self._output_weight
        async with AsyncSession(self._engine) as session:
            found = await session.exec(
                select(func.coalesce(func.sum(equivalent), 0)).where(
                    col(RunRecord.user_id) == owner,
                    col(RunRecord.started_at) >= since,
                )
            )
            return int(found.one())

    async def active_run(self, user_id: str) -> int:
        """这个用户此刻占着几个 run。

        Args:
            user_id: 用户标识。

        Returns:
            状态为 `queued` 或 `running` 的行数；用户 id 不合法时按 0 算。
        """
        owner = _parse(user_id)
        if owner is None:
            return 0
        async with AsyncSession(self._engine) as session:
            found = await session.exec(
                select(func.count())
                .select_from(RunRecord)
                .where(col(RunRecord.user_id) == owner, col(RunRecord.status).in_(ACTIVE_STATUS))
            )
            return int(found.one())


def next_reset(now: datetime) -> datetime:
    """配额下一次重置的时刻，给提示语用。

    Args:
        now: 当前时刻。

    Returns:
        明天零点。
    """
    return day_start(now) + timedelta(days=1)


def _parse(user_id: str) -> UUID | None:
    try:
        return UUID(user_id)
    except ValueError:
        return None
