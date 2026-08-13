"""管理员端点：账号与课题组。

**账号与组的管理是「对别人的操作」，因此全部锁在 `AdminUser` 后面。** 自己的那一份
（我是谁、我在哪些组）走 `/auth` 与 `/groups`，两边不共用端点。

**用量不在这里了**（2026-08-13）：`GET /admin/usage` 与它背后的账本一并撤除，
「谁花了多少」改到 Langfuse 上看。配额闸门不受影响 —— 它读的是 `runs` 表，
与这个端点从来不是同一条路。
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError

from api.error import invalid, not_found
from api.platform import Platform, get_platform
from api.schema import (
    CreateGroupRequest,
    CreateUserRequest,
    GroupResponse,
    SetActiveRequest,
    UserResponse,
)
from api.security import AdminUser
from user.repository import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

NAME_TAKEN_MESSAGE = "这个用户名已经被占用了"

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
