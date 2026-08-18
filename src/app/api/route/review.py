"""审核端点：队列与决策。

**只有 `reviewer` 与 `admin` 打得开这两条。** 反过来不成立 —— `reviewer` 碰不到账号
与配额，一样都碰不到。一旦让它顺手多拿一样，这个角色就退化成 `admin` 的别名，
而设它的全部意义正是把「决定什么能进平台目录」单独交出去。

**这里给 403 而不是 404**，与 `require_admin` 同一条理由：越权访问**他人的资源**
要伪装成 404，而「你的角色不够」不泄露任何东西 —— 端点存不存在本来就写在 `/docs` 上。

**审核管的是「别人能不能看见」，不是「作者能不能用」。** 被拒或被管理员下架的版本，
作者与组员照常可用；变化的只是平台目录这条可见性。
"""

import logging
from pathlib import PurePosixPath
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.error import invalid, not_found
from app.api.platform import Platform, get_platform
from app.api.schema import (
    DecideReviewRequest,
    ReviewResponse,
    SetCatalogEnabledRequest,
    SkillFileContentResponse,
    SkillFileEntryResponse,
)
from app.api.security import AdminUser, ReviewerUser
from app.preset.model import ResourceKind, ReviewStatus
from app.preset.review import ReviewItem

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reviews", tags=["review"])

# 队列清空之后打开这一页看到的不该是一片空白 —— 「我刚才审的那条呢」必然会问
DEFAULT_DECIDED_LIMIT = 50

REVIEW_NOT_FOUND_MESSAGE = "没有这条审核记录"

ALREADY_DECIDED_MESSAGE = "这条已经处理过了"

REASON_REQUIRED_MESSAGE = "拒绝必须写明理由，作者要照着它改"

CATALOG_REASON_REQUIRED_MESSAGE = "下架必须写明理由，作者和管理员需要知道如何恢复"

ONLY_APPROVED_CAN_TOGGLE_MESSAGE = "只有已通过审核的智能体、场景或 Skill 才能上下架"


@router.get("")
async def list_review(
    current: ReviewerUser,
    platform: Annotated[Platform, Depends(get_platform)],
    decided_limit: Annotated[int, Query(ge=0, le=200, description="附带回多少条已处理的")] = DEFAULT_DECIDED_LIMIT,
) -> list[ReviewResponse]:
    """审核队列：待审的在前（先提交的排前面），后面跟着最近处理过的那些。

    **提示词全文在每一行里** —— reviewer 要审的正是这段文字，让他再点一次去别处取
    等于把审核变成走过场。
    """
    pending = await platform.review.list_pending()
    decided = await platform.review.list_decided(limit=decided_limit)
    return [_to_response(one) for one in (*pending, *decided)]


@router.get("/{review_id}")
async def get_review(
    review_id: str,
    current: ReviewerUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> ReviewResponse:
    """读取一条 Agent 或 Skill 审核的冻结详情。"""
    return _to_response(await _require_item(platform, review_id))


@router.get("/{review_id}/files")
async def list_review_skill_files(
    review_id: str,
    current: ReviewerUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> list[SkillFileEntryResponse]:
    """列出待审或已审 Skill 版本的文件。"""
    item = await _require_skill_item(platform, review_id)
    return [
        SkillFileEntryResponse(path=one.path, size=one.size)
        for one in await platform.skill_store.list_version(item.skill_id or "", item.version)
    ]


@router.get("/{review_id}/files/content")
async def read_review_skill_file(
    review_id: str,
    path: str,
    current: ReviewerUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> SkillFileContentResponse:
    """读取待审或已审 Skill 版本的一个文件。"""
    relative = _valid_file_path(path)
    item = await _require_skill_item(platform, review_id)
    content = await platform.skill_store.read_version_file(
        item.skill_id or "",
        item.version,
        relative.as_posix(),
    )
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = None
    return SkillFileContentResponse(
        path=relative.as_posix(),
        size=len(content),
        content=text,
        is_binary=text is None,
    )


@router.post("/{review_id}", status_code=status.HTTP_202_ACCEPTED)
async def decide_review(
    review_id: str,
    request: DecideReviewRequest,
    current: ReviewerUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> ReviewResponse:
    """通过或拒绝一条待审。通过的那一版从这一刻起出现在广场上。

    **拒绝理由后端也校验。** 只靠前端拦的话，任何一次直接打接口都能留下一条没有理由的
    拒绝，而作者看到的是「被拒了，没说为什么」。

    Raises:
        ApiError: 没有这条记录、已经处理过了，或者拒绝时没写理由。
    """
    reason = None if request.reason is None else request.reason.strip()
    if not request.approved and not reason:
        raise invalid(REASON_REQUIRED_MESSAGE)

    if await platform.review.get_item(review_id) is None:
        raise not_found(REVIEW_NOT_FOUND_MESSAGE)

    if not await platform.review.decide(
        review_id,
        reviewer_id=current.user_id,
        approved=request.approved,
        # 通过时不留理由：那一栏是给作者看「该怎么改」的，通过时没有要改的东西
        reason=None if request.approved else reason,
    ):
        raise invalid(ALREADY_DECIDED_MESSAGE)

    logger.info("审核决策：review_id=%s approved=%s by=%s", review_id, request.approved, current.user_id)
    # **回读而不是拿写入的返回值拼**：拼出来的那份迟早会漏掉后加的字段，
    # 而漏掉的表现是前端某一栏空着，不报错
    decided = await platform.review.get_item(review_id)
    if decided is None:
        raise not_found(REVIEW_NOT_FOUND_MESSAGE)
    return _to_response(decided)


@router.post("/{review_id}/catalog", status_code=status.HTTP_202_ACCEPTED)
async def set_catalog_enabled(
    review_id: str,
    request: SetCatalogEnabledRequest,
    current: AdminUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> ReviewResponse:
    """上架或下架一个已过审的 Agent、场景或 Skill。"""
    reason = None if request.reason is None else request.reason.strip()
    if not request.enabled and not reason:
        raise invalid(CATALOG_REASON_REQUIRED_MESSAGE)
    item = await _require_item(platform, review_id)
    if item.review.status is not ReviewStatus.APPROVED:
        raise invalid(ONLY_APPROVED_CAN_TOGGLE_MESSAGE)
    if item.review.target_kind is ResourceKind.AGENT:
        changed = await platform.agent.set_catalog_enabled(
            item.agent_id or "",
            enabled=request.enabled,
            reason=None if request.enabled else reason,
            actor_id=current.user_id,
        )
    else:
        changed = await platform.skill.set_catalog_enabled(
            item.skill_id or "",
            enabled=request.enabled,
            reason=None if request.enabled else reason,
            actor_id=current.user_id,
        )
    if not changed:
        raise not_found(REVIEW_NOT_FOUND_MESSAGE)
    logger.info(
        "目录上下架：review_id=%s enabled=%s by=%s",
        review_id,
        request.enabled,
        current.user_id,
    )
    return _to_response(await _require_item(platform, review_id))


def _to_response(item: ReviewItem) -> ReviewResponse:
    return ReviewResponse(
        id=item.review.id,
        target_kind=item.review.target_kind,
        target_id=item.review.target_id,
        status=item.review.status,
        responsibility_confirmed=item.review.responsibility_confirmed,
        reason=item.review.reason,
        created_at=item.review.created_at,
        decided_at=item.review.decided_at,
        agent_id=item.agent_id,
        agent_name=item.agent_name,
        owner_name=item.owner_name,
        description=item.description,
        subject=item.subject,
        version=item.version,
        system_prompt=item.system_prompt,
        skill_refs=item.skill_refs,
        subagent_refs=item.subagent_refs,
        mcp_refs=item.mcp_refs,
        skill_id=item.skill_id,
        skill_name=item.skill_name,
        file_count=item.file_count,
        total_bytes=item.total_bytes,
        catalog_enabled=item.catalog_enabled,
        catalog_disabled_reason=item.catalog_disabled_reason,
        catalog_disabled_by=item.catalog_disabled_by,
        catalog_disabled_at=item.catalog_disabled_at,
    )


async def _require_item(platform: Platform, review_id: str) -> ReviewItem:
    """读取 Agent 或 Skill 审核详情，其他类型与不存在同样回 404。"""
    review = await platform.review.get(review_id)
    if review is None or review.target_kind not in {ResourceKind.AGENT, ResourceKind.SKILL}:
        raise not_found(REVIEW_NOT_FOUND_MESSAGE)
    item = await platform.review.get_item(review_id)
    if item is None:
        raise not_found(REVIEW_NOT_FOUND_MESSAGE)
    return item


async def _require_skill_item(platform: Platform, review_id: str) -> ReviewItem:
    """读取一条 Skill 审核详情。"""
    item = await _require_item(platform, review_id)
    if item.review.target_kind is not ResourceKind.SKILL or item.skill_id is None:
        raise not_found(REVIEW_NOT_FOUND_MESSAGE)
    return item


def _valid_file_path(path: str) -> PurePosixPath:
    """校验 Skill 审核预览的相对路径。"""
    relative = PurePosixPath(path)
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
        or "\\" in path
    ):
        raise invalid("Skill 文件路径不合法")
    return relative
