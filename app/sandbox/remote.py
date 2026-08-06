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
from collections.abc import AsyncIterator, Mapping
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

from event.model import RunErrorCode
from sandbox.path import PathEscapeError
from sandbox.pool import QueuePositionCallback, SandboxQueueTimeoutError

logger = logging.getLogger(__name__)

# 工具结果是 **dataclass** 而不是 dict：agent 侧拿到的是 `result.error` 这样的属性访问。
# 因此这里必须把 JSON 还原成对象 —— 直接把 dict 传回去，类型检查看不出来，
# 而 agent 第一次读字段就会 AttributeError。

DEFAULT_BROKER_URL = "http://127.0.0.1:8100"

# 文件工具几毫秒就回来；execute 最长 120 秒，加一截余量给 docker 本身的开销
DEFAULT_TIMEOUT = 30.0
EXECUTE_TIMEOUT = 180.0

# 排队可能持续几分钟，申请的流不能有读超时 —— 静默正是它的常态
ACQUIRE_TIMEOUT = httpx.Timeout(None, connect=10.0)

EXECUTION_FAILED_EXIT_CODE = 1

BAD_REQUEST = 400


class BrokerError(RuntimeError):
    """broker 不可达，或返回了预期之外的东西。

    与工具自身的失败是两回事：工具失败是 `error` 字段里的一句话，这个是链路断了。
    """


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
        found = self._tool("write", {"file_path": file_path, "content": content})
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
        )
        return EditResult(
            error=_text(found.get("error")),
            path=_text(found.get("path")),
            occurrences=_number(found.get("occurrences")),
        )

    def delete(self, file_path: str) -> DeleteResult:
        """删除文件。"""
        found = self._tool("delete", {"file_path": file_path})
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
            found = self._tool("execute", {"command": command, "timeout": timeout}, timeout=EXECUTE_TIMEOUT)
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

    def _tool(self, name: str, payload: Mapping[str, object], *, timeout: float = DEFAULT_TIMEOUT) -> dict[str, object]:
        try:
            response = self._client.post(f"/threads/{self._thread_id}/tool/{name}", json=payload, timeout=timeout)
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

    async def create(self) -> str:
        """开一个新会话。

        Returns:
            新会话的标识。

        Raises:
            BrokerError: broker 不可达。
        """
        result = await self._connection.call("POST", "/threads")
        return str(result["thread_id"])

    async def exists(self, thread_id: str) -> bool:
        """会话是否存在。"""
        result = await self._connection.call("GET", f"/threads/{thread_id}/exists")
        return bool(result.get("exists"))

    async def save(self, thread_id: str, filename: str, content: bytes) -> str:
        """把上传的文件落进会话目录。

        Args:
            thread_id: 会话标识。
            filename: 上传时带的文件名，不可信。
            content: 文件内容。

        Returns:
            落盘后的文件名，可能与上传时不同。

        Raises:
            PathEscapeError: 文件名不能作为会话目录下的一个文件。
            BrokerError: broker 不可达。
        """
        try:
            result = await self._connection.call(
                "POST",
                f"/threads/{thread_id}/save",
                json={"filename": filename, "content": _encode(content)},
            )
        except BrokerError as exc:
            # 越界判定留在 broker 侧 —— 路径规则跟着目录走，不该在两个进程里各写一份
            if str(BAD_REQUEST) in str(exc):
                raise PathEscapeError(str(exc)) from exc
            raise
        return str(result["filename"])

    async def artifact_since(self, thread_id: str, since: float) -> list[str]:
        """列出一次 run 产出的产物标识。

        产物是 workspace 的事而不是工具的事：agent 从头到尾不知道有「产物」这个概念，
        它只是往 `outputs/` 写文件，判定与编号都发生在平台这一侧。

        Args:
            thread_id: 会话标识。
            since: Unix 时间戳，通常取自这次 run 开始前。

        Returns:
            产物标识，可直接拼产物端点下载。

        Raises:
            BrokerError: broker 不可达。
        """
        result = await self._connection.call("GET", f"/threads/{thread_id}/artifacts", params={"since": since})
        found = result.get("artifacts", [])
        return [str(one) for one in found] if isinstance(found, list) else []

    async def artifact(self, artifact: str) -> bytes:
        """取回一个产物的字节。

        Args:
            artifact: 产物标识，形如 `{thread_id}/{outputs 下的相对路径}`。

        Returns:
            产物内容。

        Raises:
            BrokerError: 产物不存在，或 broker 不可达。
        """
        thread_id, _, relative = artifact.partition("/")
        response = await self._connection.raw.get(f"/threads/{thread_id}/artifacts/{relative}")
        if response.status_code != httpx.codes.OK:
            message = f"产物取不到：{artifact}"
            raise BrokerError(message)
        return response.content


class RemoteSandboxPool:
    """沙箱的申请与归还。

    Args:
        connection: 到 broker 的连接。
    """

    def __init__(self, connection: BrokerConnection) -> None:
        self._connection = connection

    async def acquire(self, thread_id: str, *, on_queued: QueuePositionCallback | None = None) -> None:
        """申请沙箱，必要时排队等待。

        排位由 broker 用流式响应推过来，**不轮询** —— 排队可能持续几分钟，这期间
        连接是静默的，直到排位真的变了才会有字节过来。

        Args:
            thread_id: 会话标识。
            on_queued: 排位回调，排位每变一次调一次。

        Raises:
            SandboxQueueTimeoutError: 排队超过上限。
            BrokerError: broker 不可达，或申请失败。
        """
        try:
            async with self._connection.raw.stream(
                "POST", f"/threads/{thread_id}/sandbox", timeout=ACQUIRE_TIMEOUT
            ) as response:
                response.raise_for_status()
                async for event, data in _sse(response):
                    if event == "queued" and on_queued is not None:
                        position = data.get("position")
                        if isinstance(position, int):
                            on_queued(position)
                    elif event == "ready":
                        return
                    elif event == "error":
                        raise _acquire_error(data)
        except httpx.HTTPError as exc:
            raise _fail(exc) from exc

        # 流走完了却既没 ready 也没 error：broker 半路没了
        message = "申请沙箱失败：broker 的响应流提前结束"
        raise BrokerError(message)

    async def release(self, thread_id: str) -> None:
        """归还沙箱。容器不销毁，留给同一会话的后续 run 复用。"""
        await self._connection.call("DELETE", f"/threads/{thread_id}/sandbox")


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
