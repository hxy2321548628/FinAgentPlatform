"""Skill 目录端点：上传、版本、共享、可见性与提审。"""

import logging
from pathlib import PurePosixPath
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from app.api.error import invalid, not_found, too_large
from app.api.platform import Platform, get_platform
from app.api.schema import (
    MySkillResponse,
    SetSharingRequest,
    SkillFileContentResponse,
    SkillFileEntryResponse,
    SkillListingResponse,
    SkillVersionResponse,
    SubmitReviewRequest,
    UpdateSkillRequest,
)
from app.api.security import CurrentUser
from app.preset.model import ResourceKind, ReviewStatus, Visibility
from app.preset.review import Review
from app.preset.skill import SkillDetail, SkillListing
from app.preset.skill_package import ValidatedSkillPackage, validate_skill_package

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/skills", tags=["skill"])

SKILL_NOT_FOUND_MESSAGE = "没有这个 Skill，或者它不是你的"
NAME_TAKEN_MESSAGE = "你已经有一个同名的 Skill 了"
NO_DRAFT_MESSAGE = "没有可发布的草稿：当前版本已经定稿了，先上传一个新版本"
NOT_RELEASED_MESSAGE = "还没有已发布的版本，先发布一版再提审"
ALREADY_PENDING_MESSAGE = "这一版已经在等审核了"
RESPONSIBILITY_MESSAGE = "要先勾上责任确认才能提审"
NOT_MY_GROUP_MESSAGE = "只能共享给自己所在的课题组"
RENAMED_MESSAGE = "Skill 的 name 由第一版冻结；改名请新建一个 Skill"
UPLOAD_TOO_LARGE_MESSAGE = "上传文件超过平台请求体上限"


@router.get("")
async def browse_catalog(
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> list[SkillListingResponse]:
    """Skills 库：每项展示最新审核通过的版本。"""
    return [_to_listing(one) for one in await platform.skill.list_catalog()]


@router.get("/available")
async def list_available(
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> list[SkillListingResponse]:
    """当前用户可挂到运行配置里的全部 Skill。"""
    return [_to_listing(one) for one in await platform.skill.list_available(current.user_id)]


@router.get("/{skill_id}/versions/{version}/files")
async def list_version_files(
    skill_id: str,
    version: int,
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> list[SkillFileEntryResponse]:
    """列出当前用户可见的一版 Skill 文件。"""
    await _require_available_version(platform, skill_id, version, current.user_id)
    return [
        SkillFileEntryResponse(path=one.path, size=one.size)
        for one in await platform.skill_store.list_version(skill_id, version)
    ]


@router.get("/{skill_id}/versions/{version}/files/content")
async def read_version_file(
    skill_id: str,
    version: int,
    path: str,
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> SkillFileContentResponse:
    """读取当前用户可见的一版 Skill 文件，二进制只返回元数据。"""
    relative = _valid_file_path(path)
    await _require_available_version(platform, skill_id, version, current.user_id)
    content = await platform.skill_store.read_version_file(skill_id, version, relative.as_posix())
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


@router.get("/mine")
async def list_mine(
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> list[MySkillResponse]:
    """我的全部 Skill，含软删行。"""
    return await _to_mine(platform, await platform.skill.list_owned(current.user_id))


@router.get("/mine/{skill_id}")
async def get_mine(
    skill_id: str,
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> MySkillResponse:
    """我的一个 Skill 全貌。"""
    detail = await platform.skill.detail(skill_id, owner_id=current.user_id)
    if detail is None:
        raise not_found(SKILL_NOT_FOUND_MESSAGE)
    return (await _to_mine(platform, [detail]))[0]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_skill(
    file: Annotated[UploadFile, File(description="ZIP 或单个 .md")],
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
    subject: Annotated[str, Form(max_length=32)] = "",
) -> MySkillResponse:
    """校验上传包后建立 Skill 与 v1 草稿，并把干净文件交给 Broker。"""
    package = await _validated(file, platform.upload_max_byte)
    created = await platform.skill.create(
        owner_id=current.user_id,
        name=package.name,
        subject=subject,
        description=package.description,
        file_count=package.file_count,
        total_bytes=package.total_bytes,
    )
    if created is None:
        raise invalid(NAME_TAKEN_MESSAGE)
    await platform.skill_store.save_version(created.id, 1, package.files)
    logger.info("上传 Skill：skill_id=%s version=1 by=%s", created.id, current.user_id)
    return await _require_mine(platform, created.id, current.user_id)


@router.post("/{skill_id}/draft")
async def write_draft(
    skill_id: str,
    file: Annotated[UploadFile, File(description="ZIP 或单个 .md")],
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> MySkillResponse:
    """上传并覆盖当前草稿；没有草稿则追加下一版。"""
    owned = await platform.skill.get(skill_id, owner_id=current.user_id)
    if owned is None or owned.is_deleted:
        raise not_found(SKILL_NOT_FOUND_MESSAGE)
    package = await _validated(file, platform.upload_max_byte)
    if package.name != owned.name:
        raise invalid(RENAMED_MESSAGE)
    draft = await platform.skill.write_draft(
        skill_id,
        owner_id=current.user_id,
        description=package.description,
        file_count=package.file_count,
        total_bytes=package.total_bytes,
    )
    if draft is None:
        raise not_found(SKILL_NOT_FOUND_MESSAGE)
    await platform.skill_store.save_version(skill_id, draft.version, package.files)
    logger.info("上传 Skill 草稿：skill_id=%s version=%s by=%s", skill_id, draft.version, current.user_id)
    return await _require_mine(platform, skill_id, current.user_id)


@router.patch("/{skill_id}")
async def update_skill(
    skill_id: str,
    request: UpdateSkillRequest,
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> MySkillResponse:
    """修改学科；name 与 description 都来自版本文件，不在这里复制一份。"""
    updated = await platform.skill.update_meta(skill_id, owner_id=current.user_id, subject=request.subject)
    if updated is None:
        raise not_found(SKILL_NOT_FOUND_MESSAGE)
    return await _require_mine(platform, skill_id, current.user_id)


@router.post("/{skill_id}/versions", status_code=status.HTTP_201_CREATED)
async def release_version(
    skill_id: str,
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> MySkillResponse:
    """发布当前草稿。"""
    await _require_owned(platform, skill_id, current.user_id)
    if await platform.skill.release(skill_id, owner_id=current.user_id) is None:
        raise invalid(NO_DRAFT_MESSAGE)
    return await _require_mine(platform, skill_id, current.user_id)


@router.put("/{skill_id}/sharing")
async def set_sharing(
    skill_id: str,
    request: SetSharingRequest,
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> MySkillResponse:
    """整块替换私有/组内可见性与共享组。"""
    await _require_owned(platform, skill_id, current.user_id)
    wanted = request.group_ids if request.visibility is Visibility.GROUP else []
    for group_id in wanted:
        if not await platform.group.is_member(group_id=group_id, user_id=current.user_id):
            raise invalid(NOT_MY_GROUP_MESSAGE)
    changed = await platform.skill.set_sharing(
        skill_id,
        owner_id=current.user_id,
        visibility=request.visibility,
        group_ids=wanted,
    )
    if not changed:
        raise not_found(SKILL_NOT_FOUND_MESSAGE)
    return await _require_mine(platform, skill_id, current.user_id)


@router.post("/{skill_id}/reviews", status_code=status.HTTP_201_CREATED)
async def submit_review(
    skill_id: str,
    request: SubmitReviewRequest,
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> MySkillResponse:
    """把最新已发布版本提交到共用审核队列。"""
    if not request.responsibility_confirmed:
        raise invalid(RESPONSIBILITY_MESSAGE)
    await _require_owned(platform, skill_id, current.user_id)
    version = await platform.skill.latest_released(skill_id, owner_id=current.user_id)
    if version is None:
        raise invalid(NOT_RELEASED_MESSAGE)
    submitted = await platform.review.submit(
        target_kind=ResourceKind.SKILL,
        target_id=version.id,
        submitted_by=current.user_id,
        responsibility_confirmed=True,
    )
    if submitted is None:
        raise invalid(ALREADY_PENDING_MESSAGE)
    logger.info("Skill 提审：skill_id=%s version=%s by=%s", skill_id, version.version, current.user_id)
    return await _require_mine(platform, skill_id, current.user_id)


@router.delete("/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_skill(
    skill_id: str,
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> None:
    """软删 Skill。"""
    if not await platform.skill.delete(skill_id, owner_id=current.user_id):
        raise not_found(SKILL_NOT_FOUND_MESSAGE)


async def _require_available_version(platform: Platform, skill_id: str, version: int, user_id: str) -> None:
    available = await platform.skill.list_available(user_id)
    if any(one.id == skill_id and one.version == version for one in available):
        return
    catalog = await platform.skill.list_catalog()
    if not any(one.id == skill_id and one.version == version for one in catalog):
        raise not_found("没有这个 Skill 版本，或者你无权查看")


def _valid_file_path(path: str) -> PurePosixPath:
    relative = PurePosixPath(path)
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
        or "\\" in path
    ):
        raise invalid("Skill 文件路径不合法")
    return relative


async def _validated(file: UploadFile, upload_max_byte: int) -> ValidatedSkillPackage:
    content = await file.read(upload_max_byte + 1)
    if len(content) > upload_max_byte:
        raise too_large(UPLOAD_TOO_LARGE_MESSAGE)
    result = validate_skill_package(content, filename=file.filename or "")
    if result.package is None:
        raise invalid("；".join(result.reasons))
    return result.package


async def _require_owned(platform: Platform, skill_id: str, user_id: str) -> None:
    owned = await platform.skill.get(skill_id, owner_id=user_id)
    if owned is None or owned.is_deleted:
        raise not_found(SKILL_NOT_FOUND_MESSAGE)


async def _require_mine(platform: Platform, skill_id: str, user_id: str) -> MySkillResponse:
    detail = await platform.skill.detail(skill_id, owner_id=user_id)
    if detail is None:
        raise not_found(SKILL_NOT_FOUND_MESSAGE)
    return (await _to_mine(platform, [detail]))[0]


async def _to_mine(platform: Platform, details: list[SkillDetail]) -> list[MySkillResponse]:
    version_ids = [version.id for one in details for version in one.versions]
    latest: dict[str, Review] = {}
    approved: set[str] = set()
    for review in await platform.review.list_for_target(version_ids, target_kind=ResourceKind.SKILL):
        latest.setdefault(review.target_id, review)
        if review.status is ReviewStatus.APPROVED:
            approved.add(review.target_id)
    return [_to_my_skill(one, latest, approved) for one in details]


def _to_my_skill(detail: SkillDetail, latest: dict[str, Review], approved: set[str]) -> MySkillResponse:
    return MySkillResponse(
        id=detail.skill.id,
        owner_name=detail.owner_name,
        name=detail.skill.name,
        subject=detail.skill.subject,
        visibility=detail.skill.visibility,
        call_count=detail.skill.call_count,
        is_deleted=detail.skill.is_deleted,
        in_catalog=any(one.id in approved for one in detail.versions),
        group_ids=detail.group_ids,
        versions=[
            SkillVersionResponse(
                id=one.id,
                version=one.version,
                status=one.status,
                description=one.description,
                file_count=one.file_count,
                total_bytes=one.total_bytes,
                created_at=one.created_at,
                released_at=one.released_at,
                review_id=None if one.id not in latest else latest[one.id].id,
                review_status=None if one.id not in latest else latest[one.id].status,
                review_reason=None if one.id not in latest else latest[one.id].reason,
            )
            for one in detail.versions
        ],
        created_at=detail.skill.created_at,
        updated_at=detail.skill.updated_at,
    )


def _to_listing(listing: SkillListing) -> SkillListingResponse:
    return SkillListingResponse(
        id=listing.id,
        owner_id=listing.owner_id,
        owner_name=listing.owner_name,
        name=listing.name,
        description=listing.description,
        subject=listing.subject,
        visibility=listing.visibility,
        call_count=listing.call_count,
        version=listing.version,
        file_count=listing.file_count,
        total_bytes=listing.total_bytes,
        source=listing.source,
        updated_at=listing.updated_at,
    )
