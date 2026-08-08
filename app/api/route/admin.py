"""管理员端点：成本看板。

**这里只出数字，不出内容。** 会话标题、提问、答复一个字都不经过这个端点 ——
架构 §6.3 说管理员多的是账号与配额的管理能力，不是看别人会话的能力，
而一个「顺手把标题也带出来」的报表正是那条边界最容易被悄悄破掉的地方。

配套一个自包含的静态页由 nginx 托管（`deploy/web/usage.html`）。做那一页的理由是
**一个没人看的 JSON 端点落不了地**；「看板」这个词本身就要求有东西可看。
它是运维页，不是教师用的产品前端 —— 后者仍无期次。
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from api.platform import Platform, get_platform
from api.schema import DayUsageResponse, UsageResponse, UserUsageResponse
from api.security import AdminUser

router = APIRouter(prefix="/admin", tags=["admin"])

# 看板默认看最近多久。一个月足够看出「谁在持续烧钱」，又不至于把首屏拉成一年的流水
DEFAULT_WINDOW_DAY = 30

# 窗口上限。再长就该去查库而不是刷一个页面 —— 这一页没有分页
MAX_WINDOW_DAY = 365


@router.get("/usage")
async def read_usage(
    current: AdminUser,
    platform: Annotated[Platform, Depends(get_platform)],
    days: Annotated[
        int, Query(ge=1, le=MAX_WINDOW_DAY, description="往前看多少天，从今天零点算起")
    ] = DEFAULT_WINDOW_DAY,
) -> UsageResponse:
    """按用户与按天两个口径给出这段时间的 token 用量。

    **窗口从「今天零点往前 days 天」算起**，与配额每日 0 点重置是同一条时间线 ——
    两处各说各的话，看板上的数就永远对不上教师看到的配额提示。
    """
    until = datetime.now(UTC)
    since = _day_start(until) - timedelta(days=days - 1)
    by_user = await platform.usage_report.by_user(since=since, until=until)
    by_day = await platform.usage_report.by_day(since=since, until=until)
    return UsageResponse(
        since=since,
        until=until,
        days=days,
        users=[
            UserUsageResponse(
                user_id=one.user_id,
                name=one.name,
                role=one.role,
                runs=one.runs,
                cache_read=one.cache_read,
                uncached=one.uncached,
                output=one.output,
            )
            for one in by_user
        ],
        daily=[
            DayUsageResponse(
                day=one.day,
                runs=one.runs,
                cache_read=one.cache_read,
                uncached=one.uncached,
                output=one.output,
            )
            for one in by_day
        ],
    )


def _day_start(now: datetime) -> datetime:
    return now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
