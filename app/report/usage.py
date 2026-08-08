"""用量报表：谁花了多少、每天花了多少。

**与 `quota/usage.py` 是两件事**：那里回答「这个人还能不能再跑一个」，永远带着
`user_id` 过滤，是闸门；这里回答「钱花在谁身上」，跨所有用户聚合，是账本。
把账本的查询塞进闸门那个类，等于给一个刻意不提供「不带 user 也能查」入口的地方
开一条旁路 —— 那条旁路一旦开出来就很难再收回去。

**统计的是所有 run，不只是成功的**：失败与取消的 run 一样烧了 token，
只算成功的会系统性地低估真实成本。

**这里只有数字，没有内容。** 会话标题、提问、答复一个字都不出现 ——
管理员看得到用量，看不到会话内容，那条边界不能被一个报表端点绕开。
"""

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import col

from run.repository import RunRecord
from user.model import UserRecord, UserRole


@dataclass(frozen=True)
class UserUsage:
    """一个用户在给定窗口内的用量。"""

    user_id: str
    name: str
    role: UserRole
    runs: int
    cache_read: int
    uncached: int
    output: int


@dataclass(frozen=True)
class DayUsage:
    """某一天的用量，跨全部用户。"""

    day: date
    runs: int
    cache_read: int
    uncached: int
    output: int


class UsageReport:
    """`runs` 表上的用量聚合。

    Args:
        engine: 到 Postgres 的异步引擎。
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def by_user(self, *, since: datetime, until: datetime) -> list[UserUsage]:
        """按用户聚合，**未命中 token 多的排在前面**。

        排序本身就是答案：看板要回答「谁花得最多」，让人自己在一屏数字里找不算回答。
        按未命中排而不是按总数 —— cache 命中那部分几乎不要钱（§6.4）。

        Args:
            since: 窗口起点（含）。
            until: 窗口终点（不含）。

        Returns:
            每个在窗口内跑过 run 的用户一行；没有则空列表。
        """
        statement = (
            select(
                col(UserRecord.id),
                col(UserRecord.name),
                col(UserRecord.role),
                func.count().label("runs"),
                func.coalesce(func.sum(col(RunRecord.tokens_cache_read)), 0).label("cache_read"),
                func.coalesce(func.sum(col(RunRecord.tokens_uncached)), 0).label("uncached"),
                func.coalesce(func.sum(col(RunRecord.tokens_output)), 0).label("output"),
            )
            .join(UserRecord, onclause=col(UserRecord.id) == col(RunRecord.user_id))
            .where(col(RunRecord.started_at) >= since, col(RunRecord.started_at) < until)
            .group_by(col(UserRecord.id), col(UserRecord.name), col(UserRecord.role))
            .order_by(func.coalesce(func.sum(col(RunRecord.tokens_uncached)), 0).desc())
        )
        # **走连接而不是 SQLModel 的 session**：这两条是只读的多列聚合，取回来的是
        # 一行行数字而不是模型对象。session.exec 的 select 重载最多认四列，
        # 而这里七列；换 session.execute 又会被 SQLModel 判成用错了 API
        async with self._engine.connect() as connection:
            found = (await connection.execute(statement)).all()
        return [
            UserUsage(
                user_id=row[0].hex,
                name=row[1],
                role=row[2],
                runs=row[3],
                cache_read=row[4],
                uncached=row[5],
                output=row[6],
            )
            for row in found
        ]

    async def by_day(self, *, since: datetime, until: datetime) -> list[DayUsage]:
        """按天聚合，从早到晚。

        Args:
            since: 窗口起点（含）。
            until: 窗口终点（不含）。

        Returns:
            窗口内有 run 的每一天一行；没有则空列表。**没有 run 的那天不占一行** ——
            补零是呈现层的事，报表不该假装那天有过一条记录。
        """
        bucket = func.date_trunc("day", col(RunRecord.started_at))
        statement = (
            select(
                bucket.label("day"),
                func.count().label("runs"),
                func.coalesce(func.sum(col(RunRecord.tokens_cache_read)), 0).label("cache_read"),
                func.coalesce(func.sum(col(RunRecord.tokens_uncached)), 0).label("uncached"),
                func.coalesce(func.sum(col(RunRecord.tokens_output)), 0).label("output"),
            )
            .where(col(RunRecord.started_at) >= since, col(RunRecord.started_at) < until)
            .group_by(bucket)
            .order_by(bucket)
        )
        async with self._engine.connect() as connection:
            found = (await connection.execute(statement)).all()
        return [
            DayUsage(day=row[0].date(), runs=row[1], cache_read=row[2], uncached=row[3], output=row[4]) for row in found
        ]
