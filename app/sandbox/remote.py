"""沙箱的远程访问：把每一次沙箱操作变成一次对 broker 的 HTTP 调用。

api 进程从此**摸不到 `docker.sock`，也摸不到宿主机上的任何 workspace 目录**。
它被 agent 生成的内容影响之后，能做的最多是发几个请求过去。

**`SandboxBackendProtocol` 这层抽象在 P0 就立住了，这里正好兑现它的价值**：
agent 侧一行不用改，换掉的只是 backend 的实现。

两种客户端不是重复，是两条不同的执行路径：

- **backend 用同步客户端**。DeepAgents 的 `a*` 方法默认实现就是
  `asyncio.to_thread(自己的同步版本)`，工具本来就跑在工作线程里 —— 写成异步
  反而要把框架那半边一起重写，而同步版本一个字都不会阻塞事件循环。
- **workspace 与 pool 用异步客户端**。它们在路由与执行器里被直接 await，
  尤其申请沙箱可能静默等上几分钟，占着一个线程等是浪费。
"""

import base64
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import cast

import httpx
from deepagents.backends.protocol import (
    DeleteResult,
    EditResult,
    ExecuteResponse,
    FileData,
    FileDownloadResponse,
    FileInfo,
    FileUploadResponse,
    GlobResult,
    GrepMatch,
    GrepResult,
    LsResult,
    ReadResult,
    SandboxBackendProtocol,
    WriteResult,
)
from langgraph.config import get_config

from event.model import RunErrorCode
from sandbox.browse import DEFAULT_MIME, Entry, Preview, Tree
from sandbox.path import PathEscapeError
from sandbox.pool import SandboxQueueTimeoutError

logger = logging.getLogger(__name__)

# 工具结果是 **dataclass** 而不是 dict：agent 侧拿到的是 `result.error` 这样的属性访问。
# 因此这里必须把 JSON 还原成对象 —— 直接把 dict 传回去，类型检查看不出来，
# 而 agent 第一次读字段就会 AttributeError。

# 排位回调是可等待的，与 broker 内部那个同步版本（sandbox/pool.py）不是一回事：
# 这一侧的回调要把排位写进 Redis 的事件流，那是个 IO 操作
type AsyncQueuePositionCallback = Callable[[int], Awaitable[None]]

DEFAULT_BROKER_URL = "http://127.0.0.1:8100"

# 文件工具几毫秒就回来；execute 最长 120 秒，加一截余量给 docker 本身的开销
DEFAULT_TIMEOUT = 30.0
EXECUTE_TIMEOUT = 180.0

# 排队可能持续几分钟，申请的流不能有读超时 —— 静默正是它的常态
ACQUIRE_TIMEOUT = httpx.Timeout(None, connect=10.0)

EXECUTION_FAILED_EXIT_CODE = 1

# 幂等键的字段名，与 broker 侧的 `ToolRequest` 对齐
IDEMPOTENCY_FIELD = "checkpoint_ns"

BAD_REQUEST = 400

# 「这个文件有问题」而不是「链路有问题」的那几个状态码，各自翻成一个本地异常
FILE_ERROR_STATUS = frozenset({httpx.codes.NOT_FOUND, httpx.codes.CONFLICT})


class BrokerError(RuntimeError):
    """broker 不可达，或返回了预期之外的东西。

    与工具自身的失败是两回事：工具失败是 `error` 字段里的一句话，这个是链路断了。
    """


class FileMissingError(FileNotFoundError):
    """工作目录里没有这个文件。

    **越界也是这一个**：路径越出会话目录与文件不存在，对调用方是同一个回答 ——
    分开说等于把这几个端点变成探测宿主机文件的工具。
    """


@dataclass(frozen=True)
class FileStat:
    """工作目录里一个文件的元信息。

    `path` 已由 broker 规范化并确认落在会话目录内 —— 它是可以直接交给 nginx 的那一个，
    请求里那个原串不是。
    """

    path: str
    size: int
    mime: str


@dataclass(frozen=True)
class RemoteFile:
    """工作目录里一个文件的字节流。

    **`chunk` 还没读**，且必须被读完或关掉，否则到 broker 的连接会一直挂着。
    交给 `StreamingResponse` 就正好。
    """

    mime: str
    # broker 给的 Content-Length。取不到时为 None —— 那时不该往下游填这个头，
    # 填一个错的比不填更糟
    size: int | None
    chunk: AsyncIterator[bytes]


def _fail(exc: httpx.HTTPError) -> BrokerError:
    """把 httpx 的异常统一成 BrokerError，并把 broker 的错误正文带上。"""
    if isinstance(exc, httpx.HTTPStatusError):
        message = f"broker 返回 {exc.response.status_code}：{exc.response.text[:200]}"
    else:
        message = f"broker 不可达：{exc}"
    return BrokerError(message)


class RemoteSandboxBackend(SandboxBackendProtocol):
    """一个会话的文件空间与执行环境，实现全在 broker 那边。

    十个方法的签名与本地实现逐字一致，因此 agent 侧看不出区别。

    Args:
        thread_id: 会话标识。
        base_url: broker 的地址。
        client: 复用的 httpx 客户端，不传则自建。
    """

    def __init__(
        self,
        thread_id: str,
        base_url: str = DEFAULT_BROKER_URL,
        client: httpx.Client | None = None,
    ) -> None:
        self._thread_id = thread_id
        self._client = client or httpx.Client(base_url=base_url.rstrip("/"), timeout=DEFAULT_TIMEOUT)

    @property
    def id(self) -> str:
        """沙箱标识。会话与沙箱一一对应，因此就是会话标识。"""
        return self._thread_id

    def ls(self, path: str) -> LsResult:
        """列出目录内容。"""
        found = self._tool("ls", {"path": path})
        return LsResult(error=_text(found.get("error")), entries=_file_info(found.get("entries")))

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        """读取文件的一段。"""
        found = self._tool("read", {"file_path": file_path, "offset": offset, "limit": limit})
        return ReadResult(
            error=_text(found.get("error")),
            file_data=cast(FileData | None, found.get("file_data")),
            total_lines=_number(found.get("total_lines")),
            start_line=_number(found.get("start_line")),
            end_line=_number(found.get("end_line")),
            next_offset=_number(found.get("next_offset")),
            no_lines_requested=bool(found.get("no_lines_requested")),
        )

    def write(self, file_path: str, content: str) -> WriteResult:
        """写入文件，已存在则覆盖。"""
        found = self._tool("write", {"file_path": file_path, "content": content}, dedupe=True)
        return WriteResult(error=_text(found.get("error")), path=_text(found.get("path")))

    def edit(self, file_path: str, old_string: str, new_string: str, replace_all: bool = False) -> EditResult:
        """替换文件里的字符串。"""
        found = self._tool(
            "edit",
            {
                "file_path": file_path,
                "old_string": old_string,
                "new_string": new_string,
                "replace_all": replace_all,
            },
            dedupe=True,
        )
        return EditResult(
            error=_text(found.get("error")),
            path=_text(found.get("path")),
            occurrences=_number(found.get("occurrences")),
        )

    def delete(self, file_path: str) -> DeleteResult:
        """删除文件。"""
        found = self._tool("delete", {"file_path": file_path}, dedupe=True)
        return DeleteResult(error=_text(found.get("error")), path=_text(found.get("path")))

    def glob(self, pattern: str, path: str | None = None) -> GlobResult:
        """按通配符找文件。"""
        found = self._tool("glob", {"pattern": pattern, "path": path})
        return GlobResult(
            error=_text(found.get("error")),
            matches=_file_info(found.get("matches")),
            truncated=bool(found.get("truncated")),
        )

    def grep(
        self, pattern: str, path: str | None = None, glob: str | None = None, *, max_count: int | None = None
    ) -> GrepResult:
        """在文件内容里找字面串。"""
        found = self._tool("grep", {"pattern": pattern, "path": path, "glob": glob, "max_count": max_count})
        return GrepResult(
            error=_text(found.get("error")),
            matches=cast(list[GrepMatch] | None, found.get("matches")),
            truncated=bool(found.get("truncated")),
        )

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        """在沙箱容器里执行 shell 命令。

        链路本身出问题也转成带错误文本的返回值，与容器执行失败一视同仁 ——
        抛出去会让整个 run 失败，而返回错误能让 LLM 自己决定下一步。
        """
        try:
            found = self._tool(
                "execute", {"command": command, "timeout": timeout}, timeout=EXECUTE_TIMEOUT, dedupe=True
            )
        except BrokerError as exc:
            return ExecuteResponse(output=f"沙箱执行失败：{exc}", exit_code=EXECUTION_FAILED_EXIT_CODE)
        return ExecuteResponse(
            output=str(found.get("output", "")),
            exit_code=_number(found.get("exit_code")),
            truncated=bool(found.get("truncated")),
        )

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        """把字节写进 workspace。批量操作允许部分成功。"""
        payload = {"files": [{"path": path, "content": _encode(content)} for path, content in files]}
        return [
            FileUploadResponse(path=one["path"], error=one.get("error"))
            for one in _files_of(self._tool("upload", payload))
        ]

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """从 workspace 取出字节。批量操作允许部分成功。"""
        return [
            FileDownloadResponse(path=one["path"], content=_decode(one.get("content")), error=one.get("error"))
            for one in _files_of(self._tool("download", {"paths": paths}))
        ]

    def _tool(
        self,
        name: str,
        payload: Mapping[str, object],
        *,
        timeout: float = DEFAULT_TIMEOUT,
        dedupe: bool = False,
    ) -> dict[str, object]:
        body = dict(payload)
        if dedupe:
            body[IDEMPOTENCY_FIELD] = _checkpoint_ns()
        try:
            response = self._client.post(f"/threads/{self._thread_id}/tool/{name}", json=body, timeout=timeout)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise _fail(exc) from exc
        parsed: dict[str, object] = response.json()
        return parsed


class RemoteBackendFactory:
    """按会话造 backend，全程共用一条到 broker 的连接。

    每个 run 各起一条连接的话，一次分析里几十次工具调用就是几十次 TCP 握手；
    共用一个客户端才有连接池。

    Args:
        base_url: broker 的地址。
        client: 复用的 httpx 客户端，不传则自建。
    """

    def __init__(self, base_url: str = DEFAULT_BROKER_URL, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(base_url=base_url.rstrip("/"), timeout=DEFAULT_TIMEOUT)

    def __call__(self, thread_id: str) -> RemoteSandboxBackend:
        """给一个会话造 backend。"""
        return RemoteSandboxBackend(thread_id, client=self._client)

    def close(self) -> None:
        """关掉共用的连接。"""
        self._client.close()


class BrokerConnection:
    """到 broker 的异步连接，给 workspace 与沙箱池共用。

    Args:
        base_url: broker 的地址。
        client: 复用的 httpx 客户端，不传则自建。
    """

    def __init__(self, base_url: str = DEFAULT_BROKER_URL, client: httpx.AsyncClient | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient(base_url=self._base_url, timeout=DEFAULT_TIMEOUT)

    @property
    def raw(self) -> httpx.AsyncClient:
        """底层客户端，给需要流式响应或原始字节的调用方。"""
        return self._client

    async def call(self, method: str, path: str, **kwargs: object) -> dict[str, object]:
        """发一次请求并把 JSON 响应取回来。

        Args:
            method: HTTP 方法。
            path: broker 上的路径。
            **kwargs: 透传给 httpx 的参数。

        Returns:
            解析后的响应体。204 无内容时是空字典。

        Raises:
            BrokerError: 连不上、超时，或返回了非 2xx。
        """
        try:
            response = await self._client.request(method, path, **kwargs)  # type: ignore[arg-type]
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise _fail(exc) from exc

        if not response.content:
            return {}
        parsed: dict[str, object] = response.json()
        return parsed

    async def aclose(self) -> None:
        """关掉连接。"""
        await self._client.aclose()

    async def __aenter__(self) -> "BrokerConnection":
        """进入上下文并返回自身。"""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """离开上下文时关掉连接。"""
        await self.aclose()


class RemoteWorkspace:
    """会话目录的远程访问。

    Args:
        connection: 到 broker 的连接。
    """

    def __init__(self, connection: BrokerConnection) -> None:
        self._connection = connection

    async def create(self, thread_id: str) -> str:
        """给一个已经落表的会话建目录。

        Args:
            thread_id: 会话标识，由 api 那边发号。

        Returns:
            同一个标识。

        Raises:
            BrokerError: broker 不可达，或标识不能作为目录名。
        """
        result = await self._connection.call("POST", "/threads", json={"thread_id": thread_id})
        return str(result["thread_id"])

    async def destroy(self, thread_id: str) -> None:
        """销毁会话的沙箱并删掉它的整个工作目录。

        **只在会话已经从表里删掉之后调**：表是「会话存不存在」的权威，
        反过来的话有一瞬间目录已经没了而会话还查得到 —— 那是个打得开却读不了的会话。

        Args:
            thread_id: 会话标识。

        Raises:
            BrokerError: broker 不可达。
        """
        await self._connection.call("DELETE", f"/threads/{thread_id}")

    async def save(self, thread_id: str, filename: str, content: bytes, directory: str = "") -> str:
        """把上传的文件落进会话目录。

        Args:
            thread_id: 会话标识。
            filename: 上传时带的文件名，不可信。
            content: 文件内容。
            directory: 落到哪个子目录，相对会话根。留空即根下；必须已存在。

        Returns:
            落盘后相对会话根的路径，可能与上传时给的不同。

        Raises:
            PathEscapeError: 文件名不能作为一个文件，或目标目录越界、不存在。
            BrokerError: broker 不可达。
        """
        try:
            result = await self._connection.call(
                "POST",
                f"/threads/{thread_id}/save",
                json={"filename": filename, "content": _encode(content), "directory": directory},
            )
        except BrokerError as exc:
            # 越界判定留在 broker 侧 —— 路径规则跟着目录走，不该在两个进程里各写一份
            if str(BAD_REQUEST) in str(exc):
                raise PathEscapeError(str(exc)) from exc
            raise
        return str(result["path"])

    async def write(self, thread_id: str, relative_path: str, content: bytes) -> None:
        """覆盖工作目录中的一个文件。"""
        try:
            response = await self._connection.raw.put(
                f"/threads/{thread_id}/workspace/file",
                json={"path": relative_path, "content": _encode(content)},
            )
        except httpx.HTTPError as exc:
            raise _fail(exc) from exc
        if response.status_code == httpx.codes.BAD_REQUEST:
            raise PathEscapeError(response.text[:200])
        if response.status_code == httpx.codes.NOT_FOUND:
            raise FileMissingError(relative_path)
        if response.status_code == httpx.codes.CONFLICT:
            raise IsADirectoryError(relative_path)
        if response.is_error:
            raise BrokerError(f"broker 返回 {response.status_code}：{response.text[:200]}")

    async def mkdir(self, thread_id: str, relative_path: str) -> None:
        """创建工作目录中的一个目录。"""
        try:
            response = await self._connection.raw.post(
                f"/threads/{thread_id}/workspace/directory",
                json={"path": relative_path},
            )
        except httpx.HTTPError as exc:
            raise _fail(exc) from exc
        if response.status_code == httpx.codes.BAD_REQUEST:
            raise PathEscapeError(response.text[:200])
        if response.status_code == httpx.codes.NOT_FOUND:
            raise FileMissingError(relative_path)
        if response.status_code == httpx.codes.CONFLICT:
            raise FileExistsError(relative_path)
        if response.is_error:
            raise BrokerError(f"broker 返回 {response.status_code}：{response.text[:200]}")

    async def tree(self, thread_id: str) -> Tree:
        """列出会话工作目录下的全部条目。

        Args:
            thread_id: 会话标识。

        Returns:
            按路径排序的条目，以及有没有被截断。

        Raises:
            BrokerError: broker 不可达，或会话标识不能作为目录名。
        """
        result = await self._connection.call("GET", f"/threads/{thread_id}/workspace/tree")
        found = result.get("entries", [])
        entries = [_to_entry(one) for one in found] if isinstance(found, list) else []
        return Tree(entries=entries, truncated=bool(result.get("truncated")))

    async def preview(self, thread_id: str, relative_path: str, *, offset: int, limit: int) -> Preview:
        """把工作目录里一个文件的开头一截当文本读出来。

        Args:
            thread_id: 会话标识。
            relative_path: 相对会话根的路径。
            offset: 从第几行开始，0-indexed。
            limit: 最多给多少行。

        Returns:
            窗口内的文本，以及它在文件里的位置。

        Raises:
            FileMissingError: 文件不存在，或路径越界。
            IsADirectoryError: 路径指向的是目录。
            BrokerError: broker 不可达。
        """
        result = await self._file_call(
            "GET",
            f"/threads/{thread_id}/workspace/preview",
            relative_path,
            params={"path": relative_path, "offset": offset, "limit": limit},
        )
        return Preview(
            text=str(result.get("text", "")),
            total_line=_number(result.get("total_line")) or 0,
            start_line=_number(result.get("start_line")) or 0,
            end_line=_number(result.get("end_line")) or 0,
            is_binary=bool(result.get("is_binary")),
            truncated=bool(result.get("truncated")),
        )

    async def stat(self, thread_id: str, relative_path: str) -> FileStat:
        """量一下工作目录里的一个文件，不取字节。

        **给「让 nginx 直接发这个文件」用**：回的路径已经规范化且确认在会话目录内，
        调用方可以直接拿去拼内部跳转。

        Args:
            thread_id: 会话标识。
            relative_path: 相对会话根的路径。

        Returns:
            规范化后的路径、字节数与内容类型。

        Raises:
            FileMissingError: 文件不存在，或路径越界。
            IsADirectoryError: 路径指向的是目录。
            BrokerError: broker 不可达。
        """
        result = await self._file_call(
            "GET",
            f"/threads/{thread_id}/workspace/stat",
            relative_path,
            params={"path": relative_path},
        )
        return FileStat(
            path=str(result.get("path", "")),
            size=_number(result.get("size")) or 0,
            mime=str(result.get("mime", DEFAULT_MIME)),
        )

    async def remove(self, thread_id: str, relative_path: str) -> None:
        """删掉工作目录里的一个文件。

        Args:
            thread_id: 会话标识。
            relative_path: 相对会话根的路径。

        Raises:
            FileMissingError: 文件不存在，或路径越界。
            IsADirectoryError: 路径指向的是目录。
            BrokerError: broker 不可达。
        """
        await self._file_call(
            "DELETE", f"/threads/{thread_id}/workspace/file", relative_path, params={"path": relative_path}
        )

    async def open(self, thread_id: str, relative_path: str) -> RemoteFile:
        """打开工作目录里一个文件的字节流。

        **不把整个文件读进内存**：这一侧只是把 broker 的响应体一段段转出去，
        api 进程的内存占用与文件大小无关。

        Args:
            thread_id: 会话标识。
            relative_path: 相对会话根的路径。

        Returns:
            一个还没读的字节流，连同它的类型与长度。**必须读完或关掉**，
            否则连接会一直挂着 —— 交给 `StreamingResponse` 即可。

        Raises:
            FileMissingError: 文件不存在，或路径越界。
            IsADirectoryError: 路径指向的是目录。
            BrokerError: broker 不可达。
        """
        request = self._connection.raw.build_request(
            "GET", f"/threads/{thread_id}/workspace/file", params={"path": relative_path}
        )
        try:
            response = await self._connection.raw.send(request, stream=True)
        except httpx.HTTPError as exc:
            raise _fail(exc) from exc
        if response.status_code != httpx.codes.OK:
            await response.aclose()
            raise _file_error(response.status_code, relative_path)
        return RemoteFile(
            mime=response.headers.get("content-type", DEFAULT_MIME),
            size=_length(response.headers.get("content-length")),
            chunk=_drain(response),
        )

    async def _file_call(
        self, method: str, path: str, relative_path: str, *, params: Mapping[str, str | int]
    ) -> dict[str, object]:
        """发一次「针对某个文件」的调用，把 broker 的状态码翻回本地异常。

        **不走 `BrokerConnection.call`**：那一条把所有非 2xx 收成同一个 `BrokerError`，
        而这里要分得开「文件不在」与「链路断了」—— 前者是 404，后者是 500。

        Raises:
            FileMissingError: 文件不存在，或路径越界。
            IsADirectoryError: 路径指向的是目录。
            BrokerError: broker 不可达，或返回了别的失败。
        """
        try:
            response = await self._connection.raw.request(method, path, params=params)
        except httpx.HTTPError as exc:
            raise _fail(exc) from exc
        if response.status_code in FILE_ERROR_STATUS:
            raise _file_error(response.status_code, relative_path)
        if response.is_error:
            message = f"broker 返回 {response.status_code}：{response.text[:200]}"
            raise BrokerError(message)
        parsed: dict[str, object] = response.json() if response.content else {}
        return parsed


class RemoteSandboxPool:
    """沙箱的申请与归还。

    Args:
        connection: 到 broker 的连接。
    """

    def __init__(self, connection: BrokerConnection) -> None:
        self._connection = connection

    async def acquire(
        self, thread_id: str, *, holder: str, on_queued: AsyncQueuePositionCallback | None = None
    ) -> None:
        """申请沙箱，必要时排队等待。

        排位由 broker 用流式响应推过来，**不轮询** —— 排队可能持续几分钟，这期间
        连接是静默的，直到排位真的变了才会有字节过来。

        Args:
            thread_id: 会话标识。
            holder: 谁在用，取 run 标识。同一个持有者重复申请是幂等的。
            on_queued: 排位回调，排位每变一次调一次。

        Raises:
            SandboxQueueTimeoutError: 排队超过上限。
            BrokerError: broker 不可达，或申请失败。
        """
        try:
            async with self._connection.raw.stream(
                "POST", f"/threads/{thread_id}/sandbox", json={"holder": holder}, timeout=ACQUIRE_TIMEOUT
            ) as response:
                response.raise_for_status()
                async for event, data in _sse(response):
                    if event == "queued" and on_queued is not None:
                        position = data.get("position")
                        if isinstance(position, int):
                            await on_queued(position)
                    elif event == "ready":
                        return
                    elif event == "error":
                        raise _acquire_error(data)
        except httpx.HTTPError as exc:
            raise _fail(exc) from exc

        # 流走完了却既没 ready 也没 error：broker 半路没了
        message = "申请沙箱失败：broker 的响应流提前结束"
        raise BrokerError(message)

    async def release(self, thread_id: str, *, holder: str) -> None:
        """按持有者归还沙箱。容器不销毁，留给同一会话的后续 run 复用。"""
        await self._connection.call("DELETE", f"/threads/{thread_id}/sandbox", params={"holder": holder})


def _acquire_error(data: dict[str, object]) -> Exception:
    """把流里的一条 error 还原成异常。"""
    message = str(data.get("message", "申请沙箱失败"))
    if data.get("code") == RunErrorCode.SANDBOX_QUEUE_TIMEOUT.value:
        return SandboxQueueTimeoutError(message)
    return BrokerError(message)


async def _sse(response: httpx.Response) -> AsyncIterator[tuple[str, dict[str, object]]]:
    """把 SSE 响应拆成 (事件名, 载荷)。

    只认 `event:` 与 `data:` 两行 —— 这条流不用 id，也不需要断线补齐：
    连接断了就是申请失败，重来一次即可。
    """
    event = ""
    async for line in response.aiter_lines():
        if line.startswith("event:"):
            event = line.removeprefix("event:").strip()
        elif line.startswith("data:"):
            yield event, json.loads(line.removeprefix("data:").strip())


def _checkpoint_ns() -> str | None:
    """取这次工具调用的 `checkpoint_ns`，作为 broker 侧的去重键。

    **这是 backend 唯一拿得到的、按调用唯一且重放稳定的东西。** `tool_call_id` 也满足
    那两个条件，但签名里没有它、middleware 也不往下传，`get_config()` 里同样没有。

    **拿不到就返回 None，去重随之关闭而不是报错**：工具也会在图之外被调用
    （测试、将来的管理动作），那时没有 LangGraph 的上下文。少一层去重只是回到没有它的
    从前，抛异常则会把一次正常的分析打断。
    """
    try:
        configurable = get_config().get("configurable", {})
    # 图之外调用时 LangGraph 抛 RuntimeError；不同版本的类型也可能不同，
    # 因此这里按「取不到」处理而不是逐个枚举异常
    except Exception:
        logger.debug("拿不到 LangGraph 的上下文，这一次不去重")
        return None
    found = configurable.get(IDEMPOTENCY_FIELD)
    return found if isinstance(found, str) else None


def _text(value: object) -> str | None:
    """取一个可能缺席的字符串字段。"""
    return value if isinstance(value, str) else None


def _number(value: object) -> int | None:
    """取一个可能缺席的整数字段。"""
    return value if isinstance(value, int) else None


def _file_info(value: object) -> list[FileInfo] | None:
    """取一列文件信息。形状由 broker 侧的同一份契约保证。"""
    return cast(list[FileInfo] | None, value) if isinstance(value, list) else None


def _encode(content: bytes) -> str:
    return base64.b64encode(content).decode("ascii")


def _decode(content: object) -> bytes | None:
    return None if content is None else base64.b64decode(str(content))


def _files_of(result: dict[str, object]) -> list[dict[str, str]]:
    found = result.get("files", [])
    return found if isinstance(found, list) else []


def _to_entry(item: object) -> Entry:
    """把 broker 回的一个目录条目解回本地形状。形状由那一侧的同一份契约保证。"""
    found = item if isinstance(item, dict) else {}
    return Entry(
        path=str(found.get("path", "")),
        is_dir=bool(found.get("is_dir")),
        size=_number(found.get("size")) or 0,
        modified_at=datetime.fromisoformat(str(found.get("modified_at"))),
    )


def _file_error(status_code: int, relative_path: str) -> Exception:
    """把 broker 的状态码翻成本地异常。"""
    if status_code == httpx.codes.CONFLICT:
        message = f"这是一个目录：{relative_path}"
        return IsADirectoryError(message)
    message = f"文件不存在：{relative_path}"
    return FileMissingError(message)


def _length(header: str | None) -> int | None:
    """解析 Content-Length。给不出来时返回 None，不猜一个数。"""
    return int(header) if header is not None and header.isdigit() else None


async def _drain(response: httpx.Response) -> AsyncIterator[bytes]:
    """把响应体一段段转出去，读完就把连接还回池子。"""
    try:
        async for chunk in response.aiter_bytes():
            yield chunk
    finally:
        await response.aclose()
