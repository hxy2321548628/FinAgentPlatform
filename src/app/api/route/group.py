"""课题组端点：浏览、名册、加人移人、申请与审批。

**「谁能管这个组」只看 `groups.owner_id` 一列。** 不是角色，也不是组内身份表 ——
当前唯一需要区分的就是「组主 / 非组主」这一刀，而一列就切得动。

**非组主碰管理动作一律 404，不是 403。** 403 等于确认了「你猜的这个组是我的」；
而组本身的存在不是秘密（浏览列表就有），所以这里 404 不会让人无从判断，
只是不额外确认归属关系。

**邀请码只出现在两个地方**：管理员建组的响应，以及组主自己的 `/groups/mine`。
浏览列表对所有登录用户开放，码一旦跟着它发出去，任何人都能把自己塞进任何组。
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.error import invalid, not_found
from app.api.platform import Platform, get_platform
from app.api.schema import (
    AddMemberRequest,
    DecideJoinRequest,
    GroupMemberResponse,
    GroupSummaryResponse,
    JoinRequestResponse,
    MyGroupResponse,
)
from app.api.security import CurrentUser
from app.auth.session import Session
from app.group.repository import Group, JoinRequestDetail

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/groups", tags=["group"])

GROUP_NOT_FOUND_MESSAGE = "没有这个组，或者它不归你管"

USER_NOT_FOUND_MESSAGE = "没有这个账号"

REQUEST_NOT_FOUND_MESSAGE = "没有这条申请"

ALREADY_MEMBER_MESSAGE = "你已经在这个组里了"

ALREADY_APPLIED_MESSAGE = "你已经申请过了，等老师处理"

ALREADY_DECIDED_MESSAGE = "这条申请已经处理过了"

OWNER_STAYS_MESSAGE = "组主不能被移出自己的组"


@router.get("")
async def browse(
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> list[GroupSummaryResponse]:
    """全部课题组，学生凭这一页挑要申请哪一个。

    没有分页 —— 一个学院的课题组是几十个量级。
    """
    return [
        GroupSummaryResponse(
            id=one.id,
            name=one.name,
            owner_name=one.owner_name,
            member_count=one.member_count,
        )
        for one in await platform.group.list_all()
    ]


# **这两个 `/mine` 必须定义在 `/{group_id}` 那几个之前**：路由按注册顺序匹配，
# 反过来的话 `mine` 会被当成一个组 id 吃掉，而症状是 404 而不是报错
@router.get("/mine")
async def my_group(
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> list[MyGroupResponse]:
    """我所属的组。**只有组主那几个带邀请码。**"""
    return [
        MyGroupResponse(
            id=one.id,
            name=one.name,
            is_owner=one.owner_id == current.user_id,
            invite_code=one.invite_code if one.owner_id == current.user_id else None,
        )
        for one in await platform.group.list_for_user(current.user_id)
    ]


@router.get("/mine/requests")
async def my_request(
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> list[JoinRequestResponse]:
    """我发起过的入组申请，最近的排前面。

    **已经处理过的也在里面**：只留待审批的话，学生看到申请消失，分不清是被否决了
    还是自己根本没点成功。
    """
    return [_to_response(one) for one in await platform.join_request.list_for_user(current.user_id)]


@router.get("/{group_id}/members")
async def list_member(
    group_id: str,
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> list[GroupMemberResponse]:
    """一个组的名册，**只有组主看得到**。

    组员之间没有共享资源，看到同组名单没有用途 —— 少一个可见面就少一份要防的泄露。
    """
    group = await _owned(platform, group_id, current)
    return [
        GroupMemberResponse(user_id=one.user_id, name=one.name, role=one.role)
        for one in await platform.group.list_member(group.id)
    ]


@router.post("/{group_id}/members")
async def add_member(
    group_id: str,
    request: AddMemberRequest,
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> list[GroupMemberResponse]:
    """按用户名把一个已有账号加进组，已经在里面时无事发生。

    Returns:
        加完之后的名册 —— 教师点一下就该看到新的名单。

    Raises:
        ApiError: 组不归你管，或没有这个账号。
    """
    group = await _owned(platform, group_id, current)
    found = await platform.user.find_by_name(request.name)
    if found is None:
        raise not_found(USER_NOT_FOUND_MESSAGE)

    added = await platform.group.add_member(group_id=group.id, user_id=found.user.id)
    if added:
        logger.info("加入名册：group_id=%s user_id=%s by=%s", group.id, found.user.id, current.user_id)
    return [
        GroupMemberResponse(user_id=one.user_id, name=one.name, role=one.role)
        for one in await platform.group.list_member(group.id)
    ]


@router.delete("/{group_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    group_id: str,
    user_id: str,
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> None:
    """把一个人移出组，不在里面时无事发生。

    **组主移不掉自己**：「我的组」那条查询走的是成员表，移出去之后这个组就再也
    找不到了 —— 连同它的邀请码。

    Raises:
        ApiError: 组不归你管，或想移的是组主自己。
    """
    group = await _owned(platform, group_id, current)
    if user_id == group.owner_id:
        raise invalid(OWNER_STAYS_MESSAGE)
    await platform.group.remove_member(group_id=group.id, user_id=user_id)
    logger.info("移出名册：group_id=%s user_id=%s by=%s", group.id, user_id, current.user_id)


@router.post("/{group_id}/requests")
async def apply(
    group_id: str,
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> JoinRequestResponse:
    """申请加入一个组，等组主处理。

    Raises:
        ApiError: 没有这个组、已经在组里，或已经挂着一条待审批。
    """
    group = await platform.group.get(group_id)
    if group is None:
        raise not_found(GROUP_NOT_FOUND_MESSAGE)
    if await platform.group.is_member(group_id=group.id, user_id=current.user_id):
        raise invalid(ALREADY_MEMBER_MESSAGE)

    created = await platform.join_request.create(group_id=group.id, user_id=current.user_id)
    if created is None:
        raise invalid(ALREADY_APPLIED_MESSAGE)

    logger.info("申请入组：group_id=%s user_id=%s", group.id, current.user_id)
    return JoinRequestResponse(
        id=created.id,
        group_id=group.id,
        group_name=group.name,
        user_id=current.user_id,
        user_name=current.name,
        status=created.status,
        created_at=created.created_at,
    )


@router.get("/{group_id}/requests")
async def list_request(
    group_id: str,
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> list[JoinRequestResponse]:
    """这个组还没处理的申请，先申请的排前面。**只有组主看得到。**"""
    group = await _owned(platform, group_id, current)
    return [_to_response(one) for one in await platform.join_request.list_pending(group.id)]


@router.post("/{group_id}/requests/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
async def decide(
    group_id: str,
    request_id: str,
    request: DecideJoinRequest,
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> None:
    """批准或否决一条申请。批准的话申请人当场进名册。

    **路径上的组 id 要真的核对**：不核对的话，一个组主拿着别人组里的申请 id
    就能替别人批。

    不回传处理后的申请：教师下一步看的是刷新过的待办列表，而那是另一个端点。

    Raises:
        ApiError: 组不归你管、没有这条申请，或它已经被处理过了。
    """
    group = await _owned(platform, group_id, current)
    found = await platform.join_request.get(request_id)
    if found is None or found.group_id != group.id:
        raise not_found(REQUEST_NOT_FOUND_MESSAGE)

    if not await platform.join_request.decide(found.id, approved=request.approved):
        raise invalid(ALREADY_DECIDED_MESSAGE)

    logger.info(
        "审批入组：group_id=%s request_id=%s approved=%s by=%s",
        group.id,
        found.id,
        request.approved,
        current.user_id,
    )


async def _owned(platform: Platform, group_id: str, current: Session) -> Group:
    """取出一个「我当组主」的组，不是我的就 404。

    Args:
        platform: 运行时。
        group_id: 组标识。
        current: 当前用户。

    Returns:
        这个组。

    Raises:
        ApiError: 组不存在，或组主不是当前用户。两者给同一个回答。
    """
    group = await platform.group.get(group_id)
    if group is None or group.owner_id != current.user_id:
        raise not_found(GROUP_NOT_FOUND_MESSAGE)
    return group


def _to_response(detail: JoinRequestDetail) -> JoinRequestResponse:
    return JoinRequestResponse(
        id=detail.id,
        group_id=detail.group_id,
        group_name=detail.group_name,
        user_id=detail.user_id,
        user_name=detail.user_name,
        status=detail.status,
        created_at=detail.created_at,
    )
