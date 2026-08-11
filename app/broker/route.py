"""broker 的端点：8 个工具、会话目录的物理访问与浏览，以及沙箱的申请与归还。

**8 个工具全部走这里**，包括 7 个不进容器的文件工具。只挡容器不挡数据的话，
api 仍能读写任意会话的文件，边界就只剩一半 —— 而 P3 的写操作去重也要落在这一层，
文件工具留在 api 侧的话那时还得再搬一次。

工作目录的浏览（列树、预览、取字节、删文件）是另一套端点，服务的是教师的侧边栏
而不是 agent，理由写在那一节上方。
"""

import asyncio
import base64
import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

from deepagents.backends.protocol import (
    DeleteResult,
    EditResult,
    ExecuteResponse,
    GlobResult,
    GrepResult,
    LsResult,
    ReadResult,
    WriteResult,
)
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from artifact.model import CollectedArtifact
from artifact.store import ArtifactStore, guess_mime
from broker.runtime import Broker, BrokerDep
from broker.schema import (
    AcquireErrorData,
    AcquireRequest,
    ArtifactCollectResponse,
    ArtifactMarkResponse,
    CollectedArtifactItem,
    CollectRequest,
    CreateThreadRequest,
    DeleteRequest,
    DownloadItem,
    DownloadRequest,
    DownloadResponse,
    EditRequest,
    ExecuteRequest,
    ExistsResponse,
    FileResult,
    GlobRequest,
    GrepRequest,
    LsRequest,
    PreviewResponse,
    QueuedData,
    ReadRequest,
    SaveRequest,
    SaveResponse,
    ThreadResponse,
    ToolRequest,
    TreeEntryItem,
    TreeResponse,
    UploadRequest,
    UploadResponse,
    WriteRequest,
)
from event.model import RunErrorCode
from sandbox.browse import DEFAULT_PREVIEW_LINE, MAX_ENTRY, preview, tree
from sandbox.path import OUTPUT_DIR, PathEscapeError, artifact_id
from sandbox.pool import SandboxQueueTimeoutError
from store.object import CONNECT_ERROR

if TYPE_CHECKING:
    from _typeshed import DataclassInstance

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/threads", tags=["broker"])

SSE_MEDIA_TYPE = "text/event-stream"


# ------------------------------------------------------------------ 会话目录
@router.post("", status_code=status.HTTP_201_CREATED)
async def create_thread(request: CreateThreadRequest, broker: BrokerDep) -> ThreadResponse:
    """给一个已经落表的会话建目录并设上磁盘配额。

    **标识由 api 给**：会话的身份长在 `threads` 表上，目录是它的副产品。
    """
    try:
        created = broker.workspace.create(request.thread_id)
    except PathEscapeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ThreadResponse(thread_id=created)


@router.get("/{thread_id}/exists")
async def thread_exists(thread_id: str, broker: BrokerDep) -> ExistsResponse:
    """会话在不在。"""
    return ExistsResponse(exists=broker.workspace.exists(thread_id))


@router.post("/{thread_id}/save", status_code=status.HTTP_201_CREATED)
async def save_file(thread_id: str, request: SaveRequest, broker: BrokerDep) -> SaveResponse:
    """把上传的文件落进会话目录。

    文件名与目标目录都来自 HTTP 请求，属于不可信输入，越界防护在 `Workspace` 里。
    """
    try:
        saved = broker.workspace.save(thread_id, request.filename, request.content, directory=request.directory)
    except PathEscapeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return SaveResponse(
        filename=saved.name,
        size=len(request.content),
        path=saved.relative_to(broker.workspace.path(thread_id)).as_posix(),
    )


# ------------------------------------------------------------------ 工作目录的浏览
#
# **与上面八个工具是两套东西。** 那八个服务 agent，路径带 `/workspace` 前缀、
# 结果按 LLM 的口味排布；这三个服务侧边栏，路径相对会话根。硬凑成一套的话，
# 「改前端显示」与「改 agent 行为」就成了同一次改动。
@router.get("/{thread_id}/workspace/tree")
async def workspace_tree(
    thread_id: str,
    broker: BrokerDep,
    limit: Annotated[int, Query(ge=1, le=MAX_ENTRY, description="最多给多少个条目")] = MAX_ENTRY,
) -> TreeResponse:
    """列出会话工作目录下的全部条目。

    遍历是同步的，丢进线程池免得占住事件循环 —— broker 同时还挂着申请沙箱的长连接。
    """
    root = _workspace_of(broker, thread_id)
    found = await asyncio.to_thread(tree, root, limit=limit)
    return TreeResponse(entries=[TreeEntryItem(**asdict(one)) for one in found.entries], truncated=found.truncated)


@router.get("/{thread_id}/workspace/preview")
async def workspace_preview(
    thread_id: str,
    broker: BrokerDep,
    path: Annotated[str, Query(min_length=1, description="相对会话根的路径")],
    offset: Annotated[int, Query(ge=0, description="从第几行开始，0-indexed")] = 0,
    limit: Annotated[int, Query(ge=1, description="最多给多少行")] = DEFAULT_PREVIEW_LINE,
) -> PreviewResponse:
    """把一个文件的开头一截当文本读出来。"""
    target = _file_at(broker, thread_id, path)
    found = await asyncio.to_thread(preview, target, offset=offset, limit=limit)
    return PreviewResponse(**asdict(found))


@router.get("/{thread_id}/workspace/file")
async def workspace_file(
    thread_id: str,
    broker: BrokerDep,
    path: Annotated[str, Query(min_length=1, description="相对会话根的路径")],
) -> FileResponse:
    """取回工作目录里一个文件的原始字节。"""
    return FileResponse(_file_at(broker, thread_id, path), media_type=guess_mime(path))


@router.delete("/{thread_id}/workspace/file", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace_file(
    thread_id: str,
    broker: BrokerDep,
    path: Annotated[str, Query(min_length=1, description="相对会话根的路径")],
) -> None:
    """删掉工作目录里的一个文件。目录删不了。"""
    try:
        broker.workspace.remove(thread_id, path)
    except (PathEscapeError, FileNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except IsADirectoryError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


def _workspace_of(broker: Broker, thread_id: str) -> Path:
    """取会话目录。

    Raises:
        HTTPException: 标识不能作为目录名。
    """
    try:
        return broker.workspace.path(thread_id)
    except PathEscapeError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


def _file_at(broker: Broker, thread_id: str, path: str) -> Path:
    """定位工作目录里的一个文件。

    **越界与不存在给同一个回答**，否则这几个端点就成了探测宿主机文件的工具。
    指向目录则是另一回事 —— 目录在树里看得见，说出来不泄露任何东西。

    Raises:
        HTTPException: 路径越界、文件不存在，或指向的是目录。
    """
    try:
        target = broker.workspace.resolve(thread_id, path)
    except PathEscapeError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if target.is_dir():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"这是一个目录：{path}")
    if not target.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"文件不存在：{path}")
    return target


@router.post("/{thread_id}/artifacts/mark")
async def mark_artifacts(thread_id: str, broker: BrokerDep) -> ArtifactMarkResponse:
    """取一次 run 的产物判定基准。

    **基准必须由这一侧给**：判据读的是宿主机上的 inode 时间戳，而调用方进程的墙钟
    与它不同源，最多差一个 tick —— 自己取一个 `time.time_ns()` 会偶发把刚写下的产物
    判成「运行之前就有的」而静默漏掉。
    """
    return ArtifactMarkResponse(since_ns=broker.backend(thread_id).artifact_mark())


@router.post("/{thread_id}/artifacts/collect")
async def collect_artifacts(thread_id: str, request: CollectRequest, broker: BrokerDep) -> ArtifactCollectResponse:
    """认领本次 run 的产物，**顺手传进对象存储**。

    上传放在这里而不是调用方那一侧：字节躺在这个进程独占的 workspace 里，
    让 api 或 worker 来传就得先把字节经 HTTP 搬过去，凭空多一跳，
    还得给它们开一条本来不需要的文件通路。

    上传是同步的（minio 客户端没有异步接口），丢进线程池免得占住事件循环。
    """
    workspace = broker.workspace.path(thread_id)
    found = broker.backend(thread_id).artifact_since(request.since_ns)
    collected = await asyncio.to_thread(
        _upload_all, broker.artifact, thread_id=thread_id, user_id=request.user_id, workspace=workspace, found=found
    )
    return ArtifactCollectResponse(artifacts=[CollectedArtifactItem(**asdict(one)) for one in collected])


def _upload_all(
    store: ArtifactStore | None, *, thread_id: str, user_id: str, workspace: Path, found: list[Path]
) -> list[CollectedArtifact]:
    """把认领到的产物逐个传上去。"""
    return [_upload_one(store, thread_id=thread_id, user_id=user_id, path=path, workspace=workspace) for path in found]


def _upload_one(
    store: ArtifactStore | None, *, thread_id: str, user_id: str, path: Path, workspace: Path
) -> CollectedArtifact:
    """传一个产物。传不上去只记一条 error，不让整次 run 失败。

    **不把上传失败升级成 run 失败**：分析已经跑完了，字节也还在 workspace 里，
    仍按旧形状下得动。为了一次存储抖动扔掉几十分钟的分析与已经烧掉的 token 不划算。
    记 error 而不是 warning，是因为它该被告警收走 —— 产物没进对象存储是要人管的。
    """
    relative = path.relative_to(workspace / OUTPUT_DIR).as_posix()
    if store is None:
        logger.error("没有配对象存储，产物只留在 workspace 里：%s", relative)
        return CollectedArtifact(
            path=artifact_id(thread_id, workspace, path), mime=guess_mime(relative), size=path.stat().st_size
        )
    try:
        return store.put(path, user_id=user_id, thread_id=thread_id, relative_path=relative)
    except CONNECT_ERROR:
        logger.error("产物传不进对象存储，只留在 workspace 里：%s", relative, exc_info=True)
        return CollectedArtifact(
            path=artifact_id(thread_id, workspace, path), mime=guess_mime(relative), size=path.stat().st_size
        )


@router.get("/{thread_id}/artifacts/{relative_path:path}")
async def download_artifact(thread_id: str, relative_path: str, broker: BrokerDep) -> FileResponse:
    """取回一个产物的字节。"""
    try:
        target = broker.workspace.artifact(thread_id, relative_path)
    except PathEscapeError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if not target.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"产物不存在：{relative_path}")
    return FileResponse(target)


# ------------------------------------------------------------------ 沙箱生命周期
@router.post("/{thread_id}/sandbox")
async def acquire_sandbox(thread_id: str, request: AcquireRequest, broker: BrokerDep) -> StreamingResponse:
    """申请沙箱，用流式响应把排队排位实时推回去。

    做成流而不是「先返回排位、再让对方轮询」：排队可能持续几分钟，轮询要么太密
    白烧 CPU、要么太疏让教师盯着一个不动的数字。流的另一头就挂在 `asyncio.Future`
    上等，一个字节都不会发，直到排位真的变了。
    """
    return StreamingResponse(_acquire_stream(thread_id, broker, request.holder), media_type=SSE_MEDIA_TYPE)


@router.delete("/{thread_id}/sandbox", status_code=status.HTTP_204_NO_CONTENT)
async def release_sandbox(
    thread_id: str,
    broker: BrokerDep,
    holder: Annotated[str, Query(min_length=1, description="谁在还，与申请时的持有者一致")],
) -> None:
    """按持有者归还沙箱。容器不销毁，留给同一会话的后续 run 复用。"""
    await broker.pool.release(thread_id, holder=holder)


async def _acquire_stream(thread_id: str, broker: Broker, holder: str) -> AsyncIterator[str]:
    """把一次申请的过程流出去：排位变化若干条，最后一条是就绪或失败。

    池的排位回调是**同步**的（它在持锁时调），没法在里面 yield，因此回调只往队列里
    塞，由这里在「队列有新排位」与「申请已完成」之间取先到的那个。两边都是真正的
    等待，不轮询。
    """
    seat: asyncio.Queue[int] = asyncio.Queue()
    acquiring = asyncio.create_task(broker.pool.acquire(thread_id, holder=holder, on_queued=seat.put_nowait))
    waiting: asyncio.Task[int] | None = None

    try:
        while True:
            waiting = asyncio.create_task(seat.get())
            await asyncio.wait({acquiring, waiting}, return_when=asyncio.FIRST_COMPLETED)
            if not waiting.done():
                break
            yield _frame("queued", QueuedData(position=waiting.result()))
            waiting = None

        # 申请已结束。排位可能与它在同一轮里入队，先补发完再报结果，
        # 否则教师会看到「前面还有 3 个」之后直接跳到就绪，中间几跳全丢
        while not seat.empty():
            yield _frame("queued", QueuedData(position=seat.get_nowait()))
        acquiring.result()
    except SandboxQueueTimeoutError as exc:
        yield _frame("error", AcquireErrorData(code=RunErrorCode.SANDBOX_QUEUE_TIMEOUT, message=str(exc)))
    # 容器起不来、磁盘满、配额设不上都得变成流里的一条 error —— 让异常逃出去的话，
    # 对端只看到连接莫名其妙断了，分不清是还在排队还是已经失败
    except Exception as exc:
        yield _frame("error", AcquireErrorData(code=RunErrorCode.INTERNAL, message=str(exc)))
    else:
        yield _frame("ready")
    finally:
        if waiting is not None:
            waiting.cancel()
        # 对端中途断开时生成器会被关掉，而申请还挂在队列里。不撤销的话，
        # 它会在没人要的时候拿到一个容器，并且永远不会有人来归还
        if not acquiring.done():
            acquiring.cancel()


def _encode(content: bytes | None) -> str | None:
    """出方向的字节编码成 base64 字符串。"""
    return None if content is None else base64.b64encode(content).decode("ascii")


def _frame(event: str, data: BaseModel | None = None) -> str:
    """拼一条 SSE 报文。"""
    payload = "{}" if data is None else data.model_dump_json()
    return f"event: {event}\ndata: {payload}\n\n"


# ------------------------------------------------------------------ 写操作去重
#
# **纯读工具不去重**（`ls` / `read` / `glob` / `grep`）：它们没有副作用，重放一次
# 得到的就是当时该得到的东西，缓存反而会把「文件后来变了」这件事藏起来。
async def _cached[Result: "DataclassInstance"](
    broker: Broker, thread_id: str, request: ToolRequest, shape: type[Result]
) -> Result | None:
    """这次调用之前跑过吗？跑过就把当时的结果原样还回去。"""
    if broker.cache is None or not request.checkpoint_ns:
        return None
    found = await broker.cache.get(thread_id, request.checkpoint_ns)
    if found is None:
        return None
    logger.info("命中去重表，不进沙箱：thread_id=%s checkpoint_ns=%s", thread_id, request.checkpoint_ns)
    return shape(**found)


async def _remember(broker: Broker, thread_id: str, request: ToolRequest, result: "DataclassInstance") -> None:
    """记下这次调用的结果。**成功与失败一视同仁** —— 只缓存成功等于没解决重放的问题。"""
    if broker.cache is None or not request.checkpoint_ns:
        return
    await broker.cache.put(thread_id, request.checkpoint_ns, asdict(result))


async def _once[Result: "DataclassInstance"](
    broker: Broker,
    thread_id: str,
    request: ToolRequest,
    shape: type[Result],
    run: Callable[[], Result],
) -> Result:
    """跑一次写操作，同一个调用重放时直接给上一次的结果。"""
    cached = await _cached(broker, thread_id, request, shape)
    if cached is not None:
        return cached
    result = run()
    await _remember(broker, thread_id, request, result)
    return result


# ------------------------------------------------------------------ 八个工具
@router.post("/{thread_id}/tool/ls")
async def tool_ls(thread_id: str, request: LsRequest, broker: BrokerDep) -> LsResult:
    """列出目录内容。"""
    return broker.backend(thread_id).ls(request.path)


@router.post("/{thread_id}/tool/read")
async def tool_read(thread_id: str, request: ReadRequest, broker: BrokerDep) -> ReadResult:
    """读取文件的一段。"""
    return broker.backend(thread_id).read(request.file_path, request.offset, request.limit)


@router.post("/{thread_id}/tool/write")
async def tool_write(thread_id: str, request: WriteRequest, broker: BrokerDep) -> WriteResult:
    """写入文件，已存在则覆盖。"""
    return await _once(
        broker,
        thread_id,
        request,
        WriteResult,
        lambda: broker.backend(thread_id).write(request.file_path, request.content),
    )


@router.post("/{thread_id}/tool/edit")
async def tool_edit(thread_id: str, request: EditRequest, broker: BrokerDep) -> EditResult:
    """替换文件里的字符串。

    **重放时 `old_string` 已经不在了**，会返回一个首次执行时没有的错误 ——
    这正是要去重的那一类。
    """
    return await _once(
        broker,
        thread_id,
        request,
        EditResult,
        lambda: broker.backend(thread_id).edit(
            request.file_path, request.old_string, request.new_string, request.replace_all
        ),
    )


@router.post("/{thread_id}/tool/delete")
async def tool_delete(thread_id: str, request: DeleteRequest, broker: BrokerDep) -> DeleteResult:
    """删除文件。**重放时文件已经没了**，同上。"""
    return await _once(
        broker, thread_id, request, DeleteResult, lambda: broker.backend(thread_id).delete(request.file_path)
    )


@router.post("/{thread_id}/tool/glob")
async def tool_glob(thread_id: str, request: GlobRequest, broker: BrokerDep) -> GlobResult:
    """按通配符找文件。"""
    return broker.backend(thread_id).glob(request.pattern, request.path)


@router.post("/{thread_id}/tool/grep")
async def tool_grep(thread_id: str, request: GrepRequest, broker: BrokerDep) -> GrepResult:
    """在文件内容里找字面串。"""
    return broker.backend(thread_id).grep(request.pattern, request.path, request.glob, max_count=request.max_count)


@router.post("/{thread_id}/tool/execute")
async def tool_execute(thread_id: str, request: ExecuteRequest, broker: BrokerDep) -> ExecuteResponse:
    """在沙箱容器里执行 shell 命令。

    命令要跑到 120 秒，同步执行会把事件循环占住，因此丢进线程池。

    **这是最需要去重的一个**：代码由 LLM 生成，可能追加写、累加计数、删文件 ——
    重放一次就多做一遍。
    """
    cached = await _cached(broker, thread_id, request, ExecuteResponse)
    if cached is not None:
        return cached
    backend = broker.backend(thread_id)
    result = await asyncio.to_thread(backend.execute, request.command, timeout=request.timeout)
    await _remember(broker, thread_id, request, result)
    return result


@router.post("/{thread_id}/tool/upload")
async def tool_upload(thread_id: str, request: UploadRequest, broker: BrokerDep) -> UploadResponse:
    """批量把字节写进 workspace。批量操作允许部分成功。"""
    written = broker.backend(thread_id).upload_files([(one.path, one.content) for one in request.files])
    return UploadResponse(files=[FileResult(path=one.path, error=one.error) for one in written])


@router.post("/{thread_id}/tool/download")
async def tool_download(thread_id: str, request: DownloadRequest, broker: BrokerDep) -> DownloadResponse:
    """批量从 workspace 取字节。批量操作允许部分成功。"""
    found = broker.backend(thread_id).download_files(request.paths)
    return DownloadResponse(
        files=[DownloadItem(path=one.path, content=_encode(one.content), error=one.error) for one in found]
    )
