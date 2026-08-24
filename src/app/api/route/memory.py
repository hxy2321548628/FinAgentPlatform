"""教师管理当前 thread 的记忆：列表、详情与物理删除。"""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.error import not_found
from app.api.platform import Platform, get_platform
from app.api.route.thread import require_thread
from app.api.schema import MemoryDetailResponse, MemoryListResponse, MemorySummaryResponse
from app.api.security import CurrentUser
from app.memory.model import MemoryCatalogEntry, MemoryRecord
from app.sandbox.remote import FileMissingError

router = APIRouter(prefix="/threads", tags=["memory"])


@router.get("/{thread_id}/memories")
async def list_memories(
    thread_id: str,
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> MemoryListResponse:
    """列出当前教师在这个 active thread 下的记忆短索引。"""
    await require_thread(platform, thread_id, current.user_id)
    try:
        found = await platform.memory.catalog(thread_id)
    except FileMissingError as exc:
        raise not_found(f"会话记忆不存在：{thread_id}") from exc
    return MemoryListResponse(items=[_summary(one) for one in found])


@router.get("/{thread_id}/memories/{slug}")
async def memory_detail(
    thread_id: str,
    slug: str,
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> MemoryDetailResponse:
    """读取当前教师的一条 thread 记忆正文。"""
    await require_thread(platform, thread_id, current.user_id)
    try:
        found = await platform.memory.detail(thread_id, slug)
    except (FileMissingError, ValueError) as exc:
        raise not_found(f"记忆不存在：{slug}") from exc
    return _detail(found)


@router.delete("/{thread_id}/memories/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(
    thread_id: str,
    slug: str,
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> None:
    """物理删除当前教师的一条 thread 记忆。"""
    await require_thread(platform, thread_id, current.user_id)
    try:
        await platform.memory.delete(thread_id, slug)
    except (FileMissingError, ValueError) as exc:
        raise not_found(f"记忆不存在：{slug}") from exc


def _summary(record: MemoryCatalogEntry) -> MemorySummaryResponse:
    return MemorySummaryResponse(
        slug=record.slug,
        name=record.name,
        description=record.description,
        type=record.type,
        updated_at=record.updated_at,
    )


def _detail(record: MemoryRecord) -> MemoryDetailResponse:
    return MemoryDetailResponse(
        slug=record.slug,
        name=record.name,
        description=record.description,
        type=record.type,
        updated_at=record.updated_at,
        content=record.body,
    )
