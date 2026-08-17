"""管理员端点：账号与课题组。

**账号与组的管理是「对别人的操作」，因此全部锁在 `AdminUser` 后面。** 自己的那一份
（我是谁、我在哪些组）走 `/auth` 与 `/groups`，两边不共用端点。

**用量不在这里了**（2026-08-13）：`GET /admin/usage` 与它背后的账本一并撤除，
「谁花了多少」改到 Langfuse 上看。配额闸门不受影响 —— 它读的是 `runs` 表，
与这个端点从来不是同一条路。

**`GET /admin/system` 是一次转发**（P11）：沙箱池活在 broker 进程里，api 这边
只有一条到它的 HTTP 连接。
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError

from app.api.error import invalid, not_found
from app.api.platform import Platform, get_platform
from app.api.schema import (
    CreateGroupRequest,
    CreateUserRequest,
    GroupResponse,
    SetActiveRequest,
    SystemStatusResponse,
    UserResponse,
)
from app.api.security import AdminUser
from app.sandbox.remote import BrokerError
from app.user.repository import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

NAME_TAKEN_MESSAGE = "这个用户名或邮箱已经被占用了"

GROUP_NAME_TAKEN_MESSAGE = "这个组名已经被占用了"

USER_NOT_FOUND_MESSAGE = "没有这个账号"


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
            email=request.email,
            dept=request.dept,
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
async def update_user(
    user_id: str,
    request: SetActiveRequest,
    current: AdminUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> UserResponse:
    """改一个账号：启停、角色、配额、院系，只动传了的那几项。

    「注册后等激活」与「被停用」在库里是同一个状态，这个端点因此同时是激活入口
    与封禁入口。

    **配额那两项按 `model_fields_set` 判断传没传，不看值是不是 None** ——
    显式传 `null` 表示「回到角色默认档」，与「这一项不改」是两件事。

    Raises:
        ApiError: 没有这个账号。
    """
    sent = request.model_fields_set
    found = True
    if request.is_active is not None:
        found = await platform.user.set_active(user_id, is_active=request.is_active)
    if found:
        found = await platform.user.update_profile(
            user_id,
            role=request.role if request.role is not None else ...,
            quota_tokens_daily=request.quota_tokens_daily if "quota_tokens_daily" in sent else ...,
            quota_concurrent_runs=request.quota_concurrent_runs if "quota_concurrent_runs" in sent else ...,
            dept=request.dept if request.dept is not None else ...,
        )
    if not found:
        raise not_found(USER_NOT_FOUND_MESSAGE)
    updated = await platform.user.get(user_id)
    if updated is None:
        raise not_found(USER_NOT_FOUND_MESSAGE)
    logger.info("管理员改账号：user_id=%s 改了=%s by=%s", user_id, sorted(sent), current.user_id)
    return _to_response(updated)


@router.get("/system")
async def system_status(
    current: AdminUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> SystemStatusResponse:
    """沙箱池此刻的占用情况。

    **api 自己答不出来** —— 池活在 broker 进程里，这里只有一条到它的 HTTP 连接，
    因此这个端点是一次转发。

    **broker 连不上时不是 500。** 那台起没起来本身就是这一页要回答的问题之一，
    把它变成一个错误页，等于在最需要看状态的时候什么都看不到。
    """
    try:
        found = await platform.connection.call("GET", "/stat")
    except BrokerError:
        logger.warning("查沙箱池状态时 broker 没应答，by=%s", current.user_id)
        return SystemStatusResponse(broker_reachable=False, in_use=0, capacity=0, queued=0)
    return SystemStatusResponse(
        broker_reachable=True,
        in_use=_count(found.get("in_use")),
        capacity=_count(found.get("capacity")),
        queued=_count(found.get("queued")),
    )


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


def _count(value: object) -> int:
    """把 broker 回来的一个字段读成计数。

    **认不出来就按 0 算，不抛。** 这条响应来自另一个进程，它的形状不该让
    「查看系统状态」这个动作失败 —— 那一页正是用来看它还在不在的。
    """
    return value if isinstance(value, int) else 0


def _to_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        dept=user.dept,
        role=user.role,
        is_active=user.is_active,
        quota_tokens_daily=user.quota_tokens_daily,
        quota_concurrent_runs=user.quota_concurrent_runs,
    )
