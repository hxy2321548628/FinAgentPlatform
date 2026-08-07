"""会话相关的端点：建会话、上传数据、提交分析。

**每一个都先用当前用户去查这个会话**，查不到就是 404 —— 不存在与不属于你在这里
是同一个回答。过滤条件长在仓储里，这里没有一句「鉴权判断」，越权返 404 是那层过滤的
副产品而不是额外工作。
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile, status

from api.error import not_found
from api.platform import Platform, get_platform
from api.schema import RunRequest, RunResponse, ThreadResponse, UploadResponse
from api.security import CurrentUser
from sandbox.path import PathEscapeError
from thread.repository import Thread

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/threads", tags=["thread"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_thread(
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> ThreadResponse:
    """开一个新会话。

    **先落表、后建目录**：表是「会话存不存在」的权威，目录是它的副产品。
    目录建失败就把那一行删掉 —— 留着就是个查得到却用不了的半个会话。
    """
    thread = await platform.thread.create(user_id=current.user_id)
    try:
        await platform.workspace.create(thread.id)
    except Exception:
        logger.warning("会话目录没建成，回滚这一行：thread_id=%s", thread.id, exc_info=True)
        await platform.thread.delete(thread.id, user_id=current.user_id)
        raise
    return ThreadResponse(id=thread.id)


@router.post("/{thread_id}/files", status_code=status.HTTP_201_CREATED)
async def upload_file(
    thread_id: str,
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
    file: Annotated[UploadFile, File(description="要分析的数据文件")],
) -> UploadResponse:
    """把数据文件放进会话的工作目录。

    文件会落在 agent 视角的 `/workspace` 根下，提示词告诉它的工作目录就是那里。
    """
    await _require_thread(platform, thread_id, current.user_id)

    content = await file.read()
    try:
        saved = await platform.workspace.save(thread_id, file.filename or "", content)
    except PathEscapeError as exc:
        # 文件名不可信，但拒绝的理由不必回给调用方 —— 那等于告诉它哪些名字能穿越
        raise not_found(f"文件名不可用：{file.filename!r}") from exc
    return UploadResponse(filename=saved, size=len(content))


@router.post("/{thread_id}/runs", status_code=status.HTTP_202_ACCEPTED)
async def submit_run(
    thread_id: str,
    request: RunRequest,
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> RunResponse:
    """提交一次分析，立刻返回。

    执行要几分钟到几十分钟，进度通过订阅事件流看，不在这个响应里等。
    """
    await _require_thread(platform, thread_id, current.user_id)

    run = await platform.submitter.submit(thread_id=thread_id, content=request.content, user_id=current.user_id)
    return RunResponse(id=run.id, thread_id=run.thread_id, status=run.status)


async def _require_thread(platform: Platform, thread_id: str, user_id: str) -> Thread:
    """确认这个会话存在**且属于当前用户**，否则 404。

    **查的是表不是目录**：目录没有归属信息，让它当权威等于把越权检查建在一个
    不知道谁是主人的东西上。
    """
    thread = await platform.thread.get(thread_id, user_id=user_id)
    if thread is None:
        message = f"会话不存在：{thread_id}"
        raise not_found(message)
    return thread
