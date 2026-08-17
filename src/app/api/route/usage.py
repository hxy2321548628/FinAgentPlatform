"""用量端点：我花了多少、全院谁花得最多。

**数字来自 Langfuse，不来自 `runs` 表。** 平台自己那份 `runs.tokens_*` 仍在逐条落库，
但它只服务配额闸门 —— 两份账本各答一个问题，谁都不去回答对方那个。

**没配 Langfuse 时返回 `available: false`，不是 500，也不是一串 0。**
一串 0 会让「没接账本」与「这个月还没人用」长得一模一样，而这两件事一个该去配环境，
一个什么都不用做。

**这里不做「本月」的定义**，窗口由调用方给或用默认的当月起点 —— 时区已经在
`quota/usage.py` 上栽过一次（窗口切在 UTC 零点、提示语却按北京时间显示），
不再在第二个地方重新发明一遍。
"""

import logging
from datetime import UTC, datetime
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends

from src.app.api.platform import Platform, get_platform
from src.app.api.schema import UsageRankingResponse, UsageResponse, UserUsageItem
from src.app.api.security import AdminUser, CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/usage", tags=["usage"])

# 排行取前多少名。**不是「全部用户」** —— 那张表给人看，一屏装不下就没人看
RANKING_LIMIT = 20


def _month_start(now: datetime) -> datetime:
    """本月起点。用量看板上的「本月」就是从这一刻算起。"""
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


@router.get("/me")
async def my_usage(
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> UsageResponse:
    """我这个月用了多少。

    Returns:
        本月的 token 与费用；没接账本时 `available` 为 false，数字均为 0。
    """
    if platform.langfuse is None:
        return UsageResponse(available=False, tokens=0, cost=0.0, observations=0)
    now = datetime.now(UTC)
    try:
        found = await platform.langfuse.of_user(current.user_id, since=_month_start(now), until=now)
    # **连不上不等于用量为零。** 外部服务抖一下就把教师的配额显示成 0，
    # 会让人以为配额被重置了
    except (httpx.HTTPError, ValueError):
        logger.warning("取本人用量时 Langfuse 没应答：user_id=%s", current.user_id)
        return UsageResponse(available=False, tokens=0, cost=0.0, observations=0)
    return UsageResponse(available=True, tokens=found.tokens, cost=found.cost, observations=found.observations)


@router.get("/ranking")
async def usage_ranking(
    current: AdminUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> UsageRankingResponse:
    """全院这个月的用量与排行。**管理能力** —— 它透出的是别人的用量。

    **名字是这里补的。** Langfuse 只认得 `user_id`，而看板上要显示的是人名 ——
    那份对照在平台库里。

    Returns:
        总量与前 20 名；没接账本时 `available` 为 false。
    """
    if platform.langfuse is None:
        return UsageRankingResponse(available=False, total=UsageResponse(available=False), items=[])
    now = datetime.now(UTC)
    since = _month_start(now)
    try:
        total = await platform.langfuse.total(since=since, until=now)
        ranking = await platform.langfuse.by_user(since=since, until=now, limit=RANKING_LIMIT)
    except (httpx.HTTPError, ValueError):
        logger.warning("取用量排行时 Langfuse 没应答：by=%s", current.user_id)
        return UsageRankingResponse(available=False, total=UsageResponse(available=False), items=[])

    names = await platform.user.names([one.user_id for one in ranking])
    return UsageRankingResponse(
        available=True,
        total=UsageResponse(available=True, tokens=total.tokens, cost=total.cost, observations=total.observations),
        items=[
            UserUsageItem(
                user_id=one.user_id,
                # **查不到名字时回落到 id，不跳过这一行。** 那多半是个已经删掉的账号，
                # 而它烧掉的 token 仍然是这个月的真实开销
                name=names.get(one.user_id, one.user_id),
                tokens=one.tokens,
                cost=one.cost,
                observations=one.observations,
            )
            for one in ranking
        ],
    )
