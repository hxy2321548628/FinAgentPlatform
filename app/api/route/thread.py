"""会话相关的端点：建会话、上传数据、提交分析。

**本期没有认证** —— 谁都能建会话、谁都能访问任何会话。用户体系与越权隔离登记在 P3。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile, status

from api.error import not_found
from api.platform import Platform, get_platform
from api.schema import RunRequest, RunResponse, ThreadResponse, UploadResponse
from sandbox.path import PathEscapeError

router = APIRouter(prefix="/threads", tags=["thread"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_thread(platform: Annotated[Platform, Depends(get_platform)]) -> ThreadResponse:
    """开一个新会话。"""
    return ThreadResponse(id=platform.workspace.create())


@router.post("/{thread_id}/files", status_code=status.HTTP_201_CREATED)
async def upload_file(
    thread_id: str,
    platform: Annotated[Platform, Depends(get_platform)],
    file: Annotated[UploadFile, File(description="要分析的数据文件")],
) -> UploadResponse:
    """把数据文件放进会话的工作目录。

    文件会落在 agent 视角的 `/workspace` 根下，提示词告诉它的工作目录就是那里。
    """
    _require_thread(platform, thread_id)

    content = await file.read()
    try:
        saved = platform.workspace.save(thread_id, file.filename or "", content)
    except PathEscapeError as exc:
        # 文件名不可信，但拒绝的理由不必回给调用方 —— 那等于告诉它哪些名字能穿越
        raise not_found(f"文件名不可用：{file.filename!r}") from exc
    return UploadResponse(filename=saved.name, size=len(content))


@router.post("/{thread_id}/runs", status_code=status.HTTP_202_ACCEPTED)
async def submit_run(
    thread_id: str,
    request: RunRequest,
    platform: Annotated[Platform, Depends(get_platform)],
) -> RunResponse:
    """提交一次分析，立刻返回。

    执行要几分钟到几十分钟，进度通过订阅事件流看，不在这个响应里等。
    """
    _require_thread(platform, thread_id)

    run = await platform.executor.submit(thread_id=thread_id, content=request.content)
    return RunResponse(id=run.id, thread_id=run.thread_id, status=run.status)


def _require_thread(platform: Platform, thread_id: str) -> None:
    if not platform.workspace.exists(thread_id):
        message = f"会话不存在：{thread_id}"
        raise not_found(message)
