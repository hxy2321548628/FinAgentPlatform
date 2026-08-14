"""用量统计：一个用户今天烧了多少 token、此刻占着几个 run。

两个数都从 `runs` 表算，走 `ix_runs_user_started` 那条索引。**不另起一份 Redis 计数器**：
那样会有两个真相源，而它们分叉的方式是静默的 —— 计数器丢一次，闸门就永远松着。

**token 按未命中部分算，`cache_read` 一律不计入。** 实测 62% 的 input 是 cache 命中，
按 input 总数扣会高估约 1.6 倍，而且**方向性地惩罚长会话** —— 会话越长命中率越高、
边际成本越低，按总数扣却扣得越狠。而长会话深度分析正是平台想鼓励的。
扣错方向比扣错数值严重得多。

**「今天」按一个显式的时区切，不按进程的本地时区**（2026-08-14 改）。原先切在 UTC
零点上，而提示语用 `.astimezone()` 把它转成进程时区再显示 —— 容器里 `TZ` 就是 UTC，
那一步什么都没转，于是**印出来的「00:00 重置」实际是北京时间早上八点**。
教师照着这句话等到零点，会发现还是提交不了，再等八小时。

两处都改：窗口切在 `QUOTA_RESET_TIMEZONE` 的零点上（默认 `Asia/Shanghai`），
提示语直接用那个时区的时刻，**中间不再有一次「转成本地」**。窗口与提示语从此是
同一个时区算出来的，不会再各说各的。
"""

from datetime import UTC, datetime, time, timedelta, tzinfo
from uuid import UUID
from zoneinfo import ZoneInfo

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

# 配额按哪个时区的零点重置。**学院在国内，默认就该是国内的零点** ——
# 「每天 0 点重置」这句话是说给教师听的，它必须在教师的钟上成立
DEFAULT_RESET_TIMEZONE = "Asia/Shanghai"


def day_start(now: datetime, *, zone: tzinfo) -> datetime:
    """当天的起点，按给定时区切。

    配额每日 0 点重置 —— 这与 `QUOTA_EXCEEDED` 的提示语「明日 0 点重置」是同一件事，
    两处不能各说各的，因此它们**共用这一个时区**。

    Args:
        now: 当前时刻。
        zone: 按哪个时区算「一天」。

    Returns:
        同一天的零点，带着 `zone` 这个时区。
    """
    return now.astimezone(zone).replace(hour=0, minute=0, second=0, microsecond=0)


class RunUsage:
    """按用户统计 `runs` 表里的用量。

    Args:
        engine: 到 Postgres 的异步引擎。
        output_weight: output token 折算成当量的权重。
        reset_zone: 「一天」按哪个时区切。**统计窗口与提示语共用它** ——
            各拿各的时区算，两边就会差出整整一个时差，而那种错读起来像「配额没重置」。
    """

    def __init__(self, engine: AsyncEngine, *, output_weight: int = 1, reset_zone: tzinfo | None = None) -> None:
        self._engine = engine
        self._output_weight = output_weight
        self._zone = reset_zone if reset_zone is not None else ZoneInfo(DEFAULT_RESET_TIMEZONE)

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
        since = day_start(now or datetime.now(UTC), zone=self._zone)
        equivalent = col(RunRecord.tokens_uncached) + col(RunRecord.tokens_output) * self._output_weight
        async with AsyncSession(self._engine) as session:
            found = await session.exec(
                select(func.coalesce(func.sum(equivalent), 0)).where(
                    col(RunRecord.user_id) == owner,
                    col(RunRecord.started_at) >= since,
                )
            )
            return int(found.one())

    def next_reset(self, now: datetime | None = None) -> datetime:
        """配额下一次重置的时刻，**已经是提示语该显示的那个时区**。

        调用方直接 `strftime` 就行，**不要再 `astimezone()` 一次** —— 那一步会把它
        转成进程的时区，而容器里那是 UTC。

        Args:
            now: 当前时刻，测试用它把「今天」挪到别处。

        Returns:
            明天零点。
        """
        return next_reset(now or datetime.now(UTC), zone=self._zone)

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


def next_reset(now: datetime, *, zone: tzinfo) -> datetime:
    """配额下一次重置的时刻，给提示语用。

    **按本地日期加一天再取零点，不是「加 24 小时」** —— 后者在有夏令时的时区上
    会错开一小时。国内没有夏令时，但这个函数不该只在国内是对的。

    Args:
        now: 当前时刻。
        zone: 按哪个时区算「一天」。

    Returns:
        明天零点，带着 `zone` 这个时区。
    """
    local = now.astimezone(zone)
    return datetime.combine(local.date() + timedelta(days=1), time.min, tzinfo=zone)


def _parse(user_id: str) -> UUID | None:
    try:
        return UUID(user_id)
    except ValueError:
        return None
