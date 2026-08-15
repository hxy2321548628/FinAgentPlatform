"""智能体目录端点：三个列表、我的那一族、提审。

**这里一个 `where` 都不拼。** 「我能看见哪些」全部由 `AgentRepository` 的三个方法
回答，端点只负责挑其中一个。本期唯一会安静失效的缺陷是「多看见了一条」——
过滤条件一旦散到端点上，漏一处就是一个没有人会来报的泄露。

**碰别人的 agent 一律 404，不是 403。** 与会话、与组管理同一条规矩：403 等于确认了
「你猜的这个 id 是存在的」，可以拿来把整个库探一遍。

**审核不在这里。** reviewer 那一族在 `route/review.py` —— 两边的准入不同，
放在一个路由器里迟早会有人把审核端点挂到 `CurrentUser` 上。
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status

from agent.config import AgentConfig, SkillReference
from api.error import invalid, not_found
from api.platform import Platform, get_platform
from api.schema import (
    AgentListingResponse,
    AgentVersionResponse,
    CreateAgentRequest,
    MyAgentResponse,
    SetSharingRequest,
    SubmitReviewRequest,
    UpdateAgentRequest,
    UpdateDraftRequest,
)
from api.security import CurrentUser
from preset.model import ReviewStatus, VersionStatus
from preset.repository import AgentDetail, AgentListing
from preset.review import Review
from preset.skill_reference import SkillReferenceError, resolve_skill_references

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents", tags=["agent"])

AGENT_NOT_FOUND_MESSAGE = "没有这个智能体，或者它不是你的"

NAME_TAKEN_MESSAGE = "你已经有一个同名的智能体了"

NO_DRAFT_MESSAGE = "没有可发布的草稿：当前版本已经定稿了，先改一次内容"

NOT_RELEASED_MESSAGE = "还没有已发布的版本，先发布一版再提审"

ALREADY_PENDING_MESSAGE = "这一版已经在等审核了"

RESPONSIBILITY_MESSAGE = "要先勾上责任确认才能提审"

NOT_MY_GROUP_MESSAGE = "只能共享给自己所在的课题组"


@router.get("")
async def browse_catalog(
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> list[AgentListingResponse]:
    """智能体广场：**只有平台目录里的那些**，即有一个版本审核通过的。

    展示的是最新那个**过审**的版本，不是最新那个已发布的版本 —— 作者发了 v3 而只审过
    v2 时，广场上仍是 v2。少了这一条，「审一次之后随便改」的实现照样能上广场。

    没有分页 —— 学院内部平台上 agent 是几十个量级。
    """
    return [_to_listing(one) for one in await platform.agent.list_catalog()]


# **`/available` 与 `/mine` 必须定义在 `/{agent_id}` 那几个之前**：路由按注册顺序
# 匹配，反过来的话它们会被当成 agent id 吃掉，而症状是 404 而不是报错
@router.get("/available")
async def list_available(
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> list[AgentListingResponse]:
    """我此刻能引用的全部：我自己的 ∪ 共享给我所在组的 ∪ 平台目录。

    **提交侧解析引用走的是同一条查询** —— 这一页看得见什么就引用得到什么，一行都不多。
    """
    return [_to_listing(one) for one in await platform.agent.list_available(current.user_id)]


@router.get("/mine")
async def list_mine(
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> list[MyAgentResponse]:
    """我的全部智能体，最近改动的排前面。**含删掉的那些**，由 `is_deleted` 标出。"""
    owned = await platform.agent.list_owned(current.user_id)
    return await _to_mine(platform, owned)


@router.get("/mine/{agent_id}")
async def get_mine(
    agent_id: str,
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> MyAgentResponse:
    """我的一个智能体的全貌。别人的与不存在的是同一个回答。

    Raises:
        ApiError: 没有这个智能体，或者它不是你的。
    """
    detail = await platform.agent.detail(agent_id, owner_id=current.user_id)
    if detail is None:
        raise not_found(AGENT_NOT_FOUND_MESSAGE)
    return (await _to_mine(platform, [detail]))[0]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_agent(
    request: CreateAgentRequest,
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> MyAgentResponse:
    """建一个智能体，连带它的 v1 草稿。建出来是私有的，共享要另点一下。

    Raises:
        ApiError: 同名的智能体你已经有一个了。
    """
    skill_refs = await _resolve_skills(platform, request.skills, current.user_id)
    created = await platform.agent.create(
        owner_id=current.user_id,
        name=request.name,
        description=request.description,
        subject=request.subject,
        system_prompt=request.system_prompt,
        skill_refs=skill_refs,
    )
    if created is None:
        raise invalid(NAME_TAKEN_MESSAGE)
    logger.info("建智能体：agent_id=%s by=%s", created.id, current.user_id)
    return await _require_mine(platform, created.id, current.user_id)


@router.patch("/{agent_id}")
async def update_agent(
    agent_id: str,
    request: UpdateAgentRequest,
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> MyAgentResponse:
    """改元信息。**不产生新版本。**

    Raises:
        ApiError: 不是你的、不存在，或新名称你已经用过了。
    """
    await _require_owned(platform, agent_id, current.user_id)
    changed = await platform.agent.update_meta(
        agent_id,
        owner_id=current.user_id,
        name=request.name,
        description=request.description,
        subject=request.subject,
    )
    if changed is None:
        raise invalid(NAME_TAKEN_MESSAGE)
    return await _require_mine(platform, agent_id, current.user_id)


@router.put("/{agent_id}/draft")
async def write_draft(
    agent_id: str,
    request: UpdateDraftRequest,
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> MyAgentResponse:
    """改草稿的内容。**已经定稿的话，这一下会追加下一个版本号的新草稿。**

    已发布的版本一个字都改不动 —— 落进 run 快照的引用要照常读得回来。

    Raises:
        ApiError: 不是你的，或者不存在。
    """
    await _require_owned(platform, agent_id, current.user_id)
    if (
        await platform.agent.write_draft(
            agent_id,
            owner_id=current.user_id,
            system_prompt=request.system_prompt,
            skill_refs=await _resolve_skills(platform, request.skills, current.user_id),
        )
        is None
    ):
        raise not_found(AGENT_NOT_FOUND_MESSAGE)
    return await _require_mine(platform, agent_id, current.user_id)


@router.post("/{agent_id}/versions", status_code=status.HTTP_201_CREATED)
async def release_version(
    agent_id: str,
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> MyAgentResponse:
    """把草稿定稿。从这一刻起组员看得见它，也引用得到它。

    **进不进广场是另一回事** —— 那要提审并通过。

    Raises:
        ApiError: 不是你的、不存在，或者当前没有可发布的草稿。
    """
    await _require_owned(platform, agent_id, current.user_id)
    if await platform.agent.release(agent_id, owner_id=current.user_id) is None:
        raise invalid(NO_DRAFT_MESSAGE)
    return await _require_mine(platform, agent_id, current.user_id)


@router.put("/{agent_id}/sharing")
async def set_sharing(
    agent_id: str,
    request: SetSharingRequest,
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> MyAgentResponse:
    """设可见性与共享给哪些组，**整块替换**。

    **只能共享给自己在里面的组。** 不查这一条的话，任何人拿一个组 id 就能把自己的
    东西塞进别人的组里 —— 那是反向的越权：不是「看见了不该看的」，是「让别人看见了
    不该看的」。

    Raises:
        ApiError: 不是你的、不存在，或者填了自己不在里面的组。
    """
    await _require_owned(platform, agent_id, current.user_id)
    mine = {one.id for one in await platform.group.list_for_user(current.user_id)}
    if not set(request.group_ids) <= mine:
        raise invalid(NOT_MY_GROUP_MESSAGE)

    if (
        await platform.agent.set_sharing(
            agent_id,
            owner_id=current.user_id,
            visibility=request.visibility,
            group_ids=request.group_ids,
        )
        is None
    ):
        raise not_found(AGENT_NOT_FOUND_MESSAGE)
    return await _require_mine(platform, agent_id, current.user_id)


@router.post("/{agent_id}/reviews", status_code=status.HTTP_201_CREATED)
async def submit_review(
    agent_id: str,
    request: SubmitReviewRequest,
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> MyAgentResponse:
    """把最新那个已发布的版本提交给审核。

    **提的是版本不是 agent**：改一版要重审一版，否则审过一次之后作者随便改都进得了
    广场。**没勾责任确认一律 422**，后端也校验 —— 只靠前端拦的话，直接打接口就绕过了。

    Raises:
        ApiError: 不是你的、不存在、还没发布过版本、没勾责任确认，或这一版已经在等审核。
    """
    if not request.responsibility_confirmed:
        raise invalid(RESPONSIBILITY_MESSAGE)

    detail = await platform.agent.detail(agent_id, owner_id=current.user_id)
    if detail is None or detail.agent.is_deleted:
        raise not_found(AGENT_NOT_FOUND_MESSAGE)

    released = [one for one in detail.versions if one.status is VersionStatus.RELEASED]
    if not released:
        raise invalid(NOT_RELEASED_MESSAGE)

    submitted = await platform.review.submit(
        target_id=released[-1].id,
        submitted_by=current.user_id,
        responsibility_confirmed=True,
    )
    if submitted is None:
        raise invalid(ALREADY_PENDING_MESSAGE)

    logger.info("提审：agent_id=%s version=%s by=%s", agent_id, released[-1].version, current.user_id)
    return await _require_mine(platform, agent_id, current.user_id)


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: str,
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> None:
    """删一个智能体：广场、组内、可引用列表里立刻都没有了。

    **软删。** run 快照里躺着这个 `agent_id`，那是历史；硬删等于往账本里挖一个洞。

    Raises:
        ApiError: 不是你的，或者不存在。
    """
    await _require_owned(platform, agent_id, current.user_id)
    await platform.agent.soft_delete(agent_id, owner_id=current.user_id)


async def _require_owned(platform: Platform, agent_id: str, user_id: str) -> None:
    """确认这个 agent 存在**且归当前用户**，否则 404。"""
    if await platform.agent.get(agent_id, owner_id=user_id) is None:
        raise not_found(AGENT_NOT_FOUND_MESSAGE)


async def _require_mine(platform: Platform, agent_id: str, user_id: str) -> MyAgentResponse:
    """写完之后回读一遍全貌。

    **回读而不是拿写入的返回值拼**：拼出来的那份迟早会漏掉后加的字段，
    而漏掉的表现是前端某一栏空着，不报错。
    """
    detail = await platform.agent.detail(agent_id, owner_id=user_id)
    if detail is None:
        raise not_found(AGENT_NOT_FOUND_MESSAGE)
    return (await _to_mine(platform, [detail]))[0]


async def _to_mine(platform: Platform, details: list[AgentDetail]) -> list[MyAgentResponse]:
    """给一批 agent 配上每个版本的审核状态。

    **审核记录一次批量取回**：作者手上几十个 agent、上百个版本，逐个查就是上百次往返。
    """
    version_ids = [version.id for one in details for version in one.versions]
    latest: dict[str, Review] = {}
    approved: set[str] = set()
    for review in await platform.review.list_for_target(version_ids):
        # `list_for_target` 按提审时间倒序，因此**第一条就是最近那一条** ——
        # 被拒之后改了再提时，作者要看到的是新那一条的状态而不是旧的拒绝理由
        latest.setdefault(review.target_id, review)
        if review.status is ReviewStatus.APPROVED:
            # **「在不在广场里」看的是有没有过审过，不是最近一条是不是通过** ——
            # 与 `list_catalog` 的条件必须是同一条，否则「我的」显示在广场里而广场上没有
            approved.add(review.target_id)
    return [_to_my_agent(one, latest, approved) for one in details]


def _to_my_agent(detail: AgentDetail, latest: dict[str, Review], approved: set[str]) -> MyAgentResponse:
    versions = [
        AgentVersionResponse(
            id=one.id,
            version=one.version,
            status=one.status,
            system_prompt=one.system_prompt,
            skill_refs=one.skill_refs,
            subagent_refs=one.subagent_refs,
            created_at=one.created_at,
            released_at=one.released_at,
            review_id=None if one.id not in latest else latest[one.id].id,
            review_status=None if one.id not in latest else latest[one.id].status,
            review_reason=None if one.id not in latest else latest[one.id].reason,
        )
        for one in detail.versions
    ]
    return MyAgentResponse(
        id=detail.agent.id,
        name=detail.agent.name,
        description=detail.agent.description,
        subject=detail.agent.subject,
        visibility=detail.agent.visibility,
        call_count=detail.agent.call_count,
        is_deleted=detail.agent.is_deleted,
        in_catalog=any(one.id in approved for one in detail.versions),
        group_ids=detail.group_ids,
        versions=versions,
        created_at=detail.agent.created_at,
        updated_at=detail.agent.updated_at,
    )


def _to_listing(listing: AgentListing) -> AgentListingResponse:
    return AgentListingResponse(
        id=listing.id,
        owner_id=listing.owner_id,
        owner_name=listing.owner_name,
        name=listing.name,
        description=listing.description,
        subject=listing.subject,
        visibility=listing.visibility,
        call_count=listing.call_count,
        version=listing.version,
        system_prompt=listing.system_prompt,
        skill_refs=listing.skill_refs,
        subagent_refs=listing.subagent_refs,
        source=listing.source,
        updated_at=listing.updated_at,
    )


async def _resolve_skills(platform: Platform, skill_ids: list[str] | None, user_id: str) -> list[SkillReference] | None:
    """按作者当前可见性把草稿选择解析成版本引用。"""
    try:
        resolved = await resolve_skill_references(
            AgentConfig(),
            skill_ids=skill_ids,
            user_id=user_id,
            resolver=platform.skill,
        )
    except SkillReferenceError as exc:
        raise invalid(str(exc)) from exc
    return resolved.skills
