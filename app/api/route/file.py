"""会话工作目录里的文件：列结构、看内容、下载、上传、删除。

侧边栏要显示的就是这几件事 —— 教师看得见 agent 写了哪些 `.py`、生成了哪些图，
点开能读，点一下能拿走。

**这个进程碰不到那些字节所在的磁盘。** 每一件都是发给 broker 的一次调用，
它是唯一持有宿主 workspace 的进程。路径越界的判定也全在那一侧 ——
规则跟着目录走，不该在两个进程里各写一份。

**这里是取回文件的唯一一条路。** 曾经还有一条按「产物」取的（产物先传进对象存储，
再按表主键下载），那是同一份字节的第二条通路：会话活着时两条都通，删掉会话之后
只剩产物那条还能取到。既然产物本就该随会话一起删干净，第二条通路就没有存在的理由了。
"""

import logging
from collections.abc import Awaitable
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from fastapi.responses import StreamingResponse

from api.error import invalid, not_found, too_large
from api.platform import Platform, get_platform
from api.route.thread import require_thread
from api.schema import (
    FileContentResponse,
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

# nginx 认这个头，把响应体换成它自己从磁盘读来的字节。**只在 nginx 后面有效** ——
# 直接跑 uvicorn 时浏览器只会收到一个空响应，因此那条路由配置关掉（见 Settings）
ACCEL_REDIRECT_HEADER = "X-Accel-Redirect"

# 内部跳转的前缀，与 nginx 那条 `internal` location 必须一致。
# 它下面就是 workspace 根，因此拼进去的路径必须已经由 broker 判过越界
ACCEL_PREFIX = "/workspace"


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
) -> Response:
    """取回一个文件的原始字节。

    有 nginx 时**这个进程一个字节都不经手**：鉴权与路径解析在这里做完，然后回一张
    `X-Accel-Redirect` 的条子，由 nginx 从挂进来的 workspace 直接把文件发给浏览器。
    api 的 worker 数量少、还要扛所有 SSE 长连接，代理大文件正是最不该占住它们的事。

    没有 nginx 时（开发机直接跑 uvicorn）退回自己转发，**边收边发不在进程里攒齐**，
    内存占用与文件大小无关。
    """
    await require_thread(platform, thread_id, current.user_id)

    if platform.file_direct_send:
        found = await _guard(path, platform.workspace.stat(thread_id, path))
        return Response(
            headers=_download_header(_accel_target(thread_id, found.path), found.path, download=download),
            media_type=found.mime,
        )

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
    file: Annotated[UploadFile, File(description="要分析的数据文件")],
    directory: Annotated[str, Form(description="落到哪个子目录，相对会话根。留空即根下；必须已存在")] = "",
) -> UploadResponse:
    """把一个数据文件放进会话的工作目录。

    不指定目录时文件落在 agent 视角的 `/workspace` 根下，提示词告诉它的工作目录就是那里。

    **一次一个。** 多文件批量要么整批退回（一个坏名字连累其余）、要么部分成功
    （那就得让「整批都失败」仍答 2xx 之外的码，否则 `curl -fsS` 这类调用方
    会以为传上去了）—— 两条都是为「一次选十个」付的复杂度，而前端一个一个发
    同样做得到，还天然有逐个的进度与重试。
    """
    await require_thread(platform, thread_id, current.user_id)
    _require_size(file, platform.upload_max_byte)

    name = file.filename or ""
    content = await file.read()
    try:
        saved = await platform.workspace.save(thread_id, name, content, directory=directory)
    except PathEscapeError as exc:
        # 文件名与目录都不可信，但拒绝的**理由**不必回给调用方 ——
        # 那等于告诉它哪些名字能穿越
        logger.info("上传被拒：thread_id=%s filename=%r directory=%r", thread_id, name, directory)
        raise not_found(f"文件名或目标目录不可用：{name!r}") from exc
    return UploadResponse(filename=saved.rsplit("/", maxsplit=1)[-1], path=saved, size=len(content))


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


def _require_size(file: UploadFile, limit: int) -> None:
    """确认这个文件没超过上限。

    **在读字节之前拦**：`read()` 是整块进内存的（之后还要 base64 一次交给 broker），
    读出来再判等于内存已经吃掉了。

    Raises:
        ApiError: 超过上限。
    """
    size = file.size or 0
    if size > limit:
        raise too_large(f"文件太大了（{size} 字节），单次上限是 {limit} 字节")


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


def _accel_target(thread_id: str, relative_path: str) -> str:
    """拼一条指向 workspace 的内部跳转。

    **路径要编码**：nginx 会对这个头做一次 unescape，中文文件名不编码的话到它那里
    就散了。`safe=""` 连 `/` 也编掉不行 —— 目录层级得留着，那正是 nginx 要走的路径。

    Args:
        thread_id: 会话标识。
        relative_path: broker 规范化过的相对路径，已确认落在会话目录内。

    Returns:
        形如 `/workspace/{会话}/{路径}` 的 URI，只在 nginx 那条 `internal` location 有效。
    """
    return f"{ACCEL_PREFIX}/{quote(thread_id)}/{quote(relative_path)}"


def _download_header(target: str, relative_path: str, *, download: bool) -> dict[str, str]:
    """拼直发那条路的响应头。

    **不带 `Content-Length`**：字节由 nginx 发，长度也该由它算。这里报一个数，
    与它实际发出去的对不上时，浏览器那一侧会挂在一个永远收不满的响应上。
    """
    header = {ACCEL_REDIRECT_HEADER: target}
    if download:
        header["Content-Disposition"] = _attachment(relative_path.rsplit("/", maxsplit=1)[-1])
    return header


def _attachment(filename: str) -> str:
    """拼一个让浏览器另存为的 `Content-Disposition`。

    只给 RFC 5987 的 `filename*`：中文文件名是常态，而老式的 `filename=` 只认
    latin-1，塞中文进去要么乱码要么让整个头不合法。
    """
    return f"attachment; filename*=UTF-8''{quote(filename, safe='')}"
