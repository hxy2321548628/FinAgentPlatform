"""会话工作目录里的文件：列结构、看内容、下载、上传、删除。

侧边栏要显示的就是这几件事 —— 教师看得见 agent 写了哪些 `.py`、生成了哪些图，
点开能读，点一下能拿走。

**这个进程碰不到那些字节所在的磁盘。** 每一件都是发给 broker 的一次调用，
它是唯一持有宿主 workspace 的进程。路径越界的判定也全在那一侧 ——
规则跟着目录走，不该在两个进程里各写一份。

**与产物下载（`route/artifact.py`）是两条路，不是重复。** 产物是「某次 run 认领过的
东西」，身份长在 `artifacts` 表上、字节在对象存储里，因此下载走 nginx 直发；
这里说的是「工作目录此刻长什么样」，字节只在宿主机上，只能一段段转出去。
同一张图可能两条路都能取到，那是它确实既是文件也是产物。
"""

import logging
from collections.abc import Awaitable
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from fastapi.responses import StreamingResponse

from api.error import invalid, not_found, too_large
from api.platform import Platform, get_platform
from api.route.thread import require_thread
from api.schema import (
    FileContentResponse,
    SavedFileResponse,
    UploadResponse,
    WorkspaceEntryResponse,
    WorkspaceTreeResponse,
)
from api.security import CurrentUser
from sandbox.browse import DEFAULT_PREVIEW_LINE
from sandbox.path import PathEscapeError
from sandbox.remote import FileMissingError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/threads", tags=["file"])

# 路径走查询参数而不是路径段。文件名里带 `/`、`#`、`?` 与中文都是常事，
# 塞进路径段要在两侧各写一遍转义，而错一次就是一个打不开的文件
PathParam = Annotated[str, Query(min_length=1, description="相对会话根的路径，取自目录树里的 path")]


@router.get("/{thread_id}/files")
async def list_files(
    thread_id: str,
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> WorkspaceTreeResponse:
    """列出这个会话工作目录下的全部文件与目录。"""
    await require_thread(platform, thread_id, current.user_id)

    found = await platform.workspace.tree(thread_id)
    return WorkspaceTreeResponse(
        entries=[
            WorkspaceEntryResponse(path=one.path, is_dir=one.is_dir, size=one.size, modified_at=one.modified_at)
            for one in found.entries
        ],
        truncated=found.truncated,
    )


@router.get("/{thread_id}/files/content")
async def read_file(
    thread_id: str,
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
    path: PathParam,
    offset: Annotated[int, Query(ge=0, description="从第几行开始，0-indexed")] = 0,
    limit: Annotated[int, Query(ge=1, le=DEFAULT_PREVIEW_LINE, description="最多给多少行")] = DEFAULT_PREVIEW_LINE,
) -> FileContentResponse:
    """读一个文件的一段内容，给代码查看器用。

    **按行分页而不是整个文件发过来**：教师点开的可能是一个几百 MB 的 csv。
    二进制文件不在这里返回内容，`is_binary` 为真时改用 `/files/raw`。
    """
    await require_thread(platform, thread_id, current.user_id)

    found = await _guard(path, platform.workspace.preview(thread_id, path, offset=offset, limit=limit))
    return FileContentResponse(
        path=path,
        text=found.text,
        total_line=found.total_line,
        start_line=found.start_line,
        end_line=found.end_line,
        is_binary=found.is_binary,
        truncated=found.truncated,
    )


@router.get("/{thread_id}/files/raw")
async def download_file(
    thread_id: str,
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
    path: PathParam,
    download: Annotated[bool, Query(description="真则让浏览器另存为，假则内联展示（图片直接塞 <img>）")] = False,
) -> StreamingResponse:
    """取回一个文件的原始字节。

    **边收边发，不在这个进程里攒齐**：内存占用与文件大小无关。
    """
    await require_thread(platform, thread_id, current.user_id)

    opened = await _guard(path, platform.workspace.open(thread_id, path))
    header = {} if opened.size is None else {"Content-Length": str(opened.size)}
    if download:
        header["Content-Disposition"] = _attachment(path.rsplit("/", maxsplit=1)[-1])
    return StreamingResponse(opened.chunk, media_type=opened.mime, headers=header)


@router.post("/{thread_id}/files", status_code=status.HTTP_201_CREATED)
async def upload_file(
    thread_id: str,
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
    file: Annotated[list[UploadFile], File(description="要分析的数据文件，可以给多个")],
    directory: Annotated[str, Form(description="落到哪个子目录，相对会话根。留空即根下；必须已存在")] = "",
) -> UploadResponse:
    """把数据文件放进会话的工作目录。

    不指定目录时文件落在 agent 视角的 `/workspace` 根下，提示词告诉它的工作目录就是那里。

    **字段名仍是 `file`，给多个就是多个** —— 单文件的老调用方一个字都不用改。

    **一个都没落上盘时是 422，不是 201。** 部分成功给 201 是为了不让一个坏名字
    连累同批的其他文件；但整批都没成还答 201，就等于让 `curl -fsS` 这类
    「非 2xx 才算失败」的调用方以为上传成功了 —— 验收脚本正是这么判的。
    """
    await require_thread(platform, thread_id, current.user_id)
    _require_size(file, platform.upload_max_byte)

    saved = [await _save_one(platform, thread_id, one, directory) for one in file]
    if all(one.error for one in saved):
        raise invalid(f"没有一个文件落上盘：{saved[0].error}")
    return UploadResponse(files=saved)


@router.delete("/{thread_id}/files", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(
    thread_id: str,
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
    path: PathParam,
) -> None:
    """删掉工作目录里的一个文件。

    **目录删不了**：那会连着里面的东西一起没，而侧边栏上的一下点击看不出这个后果。
    """
    await require_thread(platform, thread_id, current.user_id)

    await _guard(path, platform.workspace.remove(thread_id, path))


async def _save_one(platform: Platform, thread_id: str, file: UploadFile, directory: str) -> SavedFileResponse:
    """落一个文件。**它失败不牵连同批的其他文件** —— 逐个带 error 回去。"""
    name = file.filename or ""
    content = await file.read()
    try:
        saved = await platform.workspace.save(thread_id, name, content, directory=directory)
    except PathEscapeError:
        # 文件名与目录都不可信，但拒绝的**理由**不必回给调用方 ——
        # 那等于告诉它哪些名字能穿越
        logger.info("上传被拒：thread_id=%s filename=%r directory=%r", thread_id, name, directory)
        return SavedFileResponse(filename=name or "(无名)", size=len(content), error="文件名或目标目录不可用")
    return SavedFileResponse(filename=name, path=saved, size=len(content))


def _require_size(file: list[UploadFile], limit: int) -> None:
    """确认这一批加起来没超过上限。

    **在读字节之前拦**：读出来再判等于已经把内存吃掉了。算的是这一批的总和而不是
    单个文件 —— nginx 的 `client_max_body_size` 管的也是整个请求体，两道闸口径一致
    才不会出现「过了外面那道、卡在里面这道」。

    Raises:
        ApiError: 超过上限。
    """
    total = sum(one.size or 0 for one in file)
    if total > limit:
        raise too_large(f"上传的文件太大了（{total} 字节），单次上限是 {limit} 字节")


async def _guard[Result](path: str, call: Awaitable[Result]) -> Result:
    """跑一次针对某个文件的调用，把 broker 那边的失败翻成对外的回答。

    Raises:
        ApiError: 文件不存在或路径越界（404），或指向的是目录（422）。
    """
    try:
        return await call
    except FileMissingError as exc:
        # 越界与不存在给同一个回答，否则这个端点就成了探测宿主机文件的工具
        raise not_found(f"文件不存在：{path}") from exc
    except IsADirectoryError as exc:
        raise invalid(f"这是一个目录，不是文件：{path}") from exc


def _attachment(filename: str) -> str:
    """拼一个让浏览器另存为的 `Content-Disposition`。

    只给 RFC 5987 的 `filename*`：中文文件名是常态，而老式的 `filename=` 只认
    latin-1，塞中文进去要么乱码要么让整个头不合法。
    """
    return f"attachment; filename*=UTF-8''{quote(filename, safe='')}"
