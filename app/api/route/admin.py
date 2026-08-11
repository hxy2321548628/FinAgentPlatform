"""管理员端点：账号、课题组与成本看板。

**成本看板只出数字，不出内容。** 会话标题、提问、答复一个字都不经过这个端点 ——
架构 §6.3 说管理员多的是账号与配额的管理能力，不是看别人会话的能力，
而一个「顺手把标题也带出来」的报表正是那条边界最容易被悄悄破掉的地方。

**账号与组的管理是「对别人的操作」，因此全部锁在 `AdminUser` 后面。** 自己的那一份
（我是谁、我在哪些组）走 `/auth` 与 `/groups`，两边不共用端点。

配套一个自包含的静态页由 nginx 托管（`deploy/web/usage.html`）。做那一页的理由是
**一个没人看的 JSON 端点落不了地**；「看板」这个词本身就要求有东西可看。
它是运维页，不是教师用的产品前端 —— 后者仍无期次。
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.exc import IntegrityError

from api.error import invalid, not_found
from api.platform import Platform, get_platform
from api.schema import (
    CreateGroupRequest,
    CreateUserRequest,
    DayUsageResponse,
    GroupResponse,
    SetActiveRequest,
    UsageResponse,
    UserResponse,
    UserUsageResponse,
)
from api.security import AdminUser
from user.repository import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

NAME_TAKEN_MESSAGE = "这个用户名已经被占用了"

GROUP_NAME_TAKEN_MESSAGE = "这个组名已经被占用了"

USER_NOT_FOUND_MESSAGE = "没有这个账号"

# 看板默认看最近多久。一个月足够看出「谁在持续烧钱」，又不至于把首屏拉成一年的流水
DEFAULT_WINDOW_DAY = 30

# 窗口上限。再长就该去查库而不是刷一个页面 —— 这一页没有分页
MAX_WINDOW_DAY = 365


@router.post("/users")
async def create_user(
    request: CreateUserRequest,
    current: AdminUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> UserResponse:
    """建一个账号。**教师的账号只能从这里来。**"""
    try:
        user = await platform.user.create(
            name=request.name,
            password_hash=platform.password.hash(request.password),
            role=request.role,
        )
    except IntegrityError as error:
        raise invalid(NAME_TAKEN_MESSAGE) from error

    logger.info("管理员建号：user_id=%s role=%s by=%s", user.id, user.role.value, current.user_id)
    return _to_response(user)


@router.get("/users")
async def list_user(
    current: AdminUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> list[UserResponse]:
    """全部账号，最近建的排在前面 —— 等激活的那几个人永远在最上面。"""
    return [_to_response(one) for one in await platform.user.list_all()]


@router.patch("/users/{user_id}")
async def set_active(
    user_id: str,
    request: SetActiveRequest,
    current: AdminUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> UserResponse:
    """启用或停用一个账号。

    「注册后等激活」与「被停用」在库里是同一个状态，这个端点因此同时是激活入口
    与封禁入口。

    Raises:
        ApiError: 没有这个账号。
    """
    if not await platform.user.set_active(user_id, is_active=request.is_active):
        raise not_found(USER_NOT_FOUND_MESSAGE)
    updated = await platform.user.get(user_id)
    if updated is None:
        raise not_found(USER_NOT_FOUND_MESSAGE)
    logger.info("管理员启停账号：user_id=%s is_active=%s by=%s", user_id, request.is_active, current.user_id)
    return _to_response(updated)


@router.post("/groups")
async def create_group(
    request: CreateGroupRequest,
    current: AdminUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> GroupResponse:
    """建一个课题组并指定组主。

    **组主不限角色**：管理员自己带一个组是合理的，而把学生设成组主属于操作失误，
    不是系统要防的攻击 —— 为它加一道校验，换来的是「管理员不能给自己建组」。

    Raises:
        ApiError: 组主不存在，或组名已被占用。
    """
    if await platform.user.get(request.owner_id) is None:
        raise not_found(USER_NOT_FOUND_MESSAGE)
    try:
        group = await platform.group.create(name=request.name, owner_id=request.owner_id)
    except IntegrityError as error:
        raise invalid(GROUP_NAME_TAKEN_MESSAGE) from error

    logger.info("管理员建组：group_id=%s owner_id=%s by=%s", group.id, group.owner_id, current.user_id)
    return GroupResponse(id=group.id, name=group.name, owner_id=group.owner_id, invite_code=group.invite_code)


def _to_response(user: User) -> UserResponse:
    return UserResponse(id=user.id, name=user.name, role=user.role, is_active=user.is_active)


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
