"""写操作去重在端点上的测试：同一个键重放时不进沙箱，纯读工具不受影响。

**用真 broker 路由 + 真 Redis**，只把沙箱换成会数次数的替身 —— 要验的正是
「第二次调用没有落到沙箱上」，而那件事只有数次数才看得见。
"""

import asyncio
import io
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

import httpx
import pytest
from redis.asyncio import Redis
from starlette.requests import ClientDisconnect
from starlette.types import Message, Scope

from app.broker.app import create_app
from app.broker.cache import ToolCache
from app.broker.route import _file_chunks, destroy_thread, tool_execute, tool_write, workspace_file
from app.broker.runtime import Broker
from app.broker.schema import ExecuteRequest, WriteRequest
from app.broker.skill import SkillStore
from app.sandbox.container import CommandResult
from app.sandbox.workspace import Workspace

THREAD = "thread-dedupe"

NS = "tools:fd422cb9-d8b8-c0ae-510d-64ed2e099a1c"

BROKER_URL = "http://broker.test"


class CountingContainer:
    """会数「进了几次沙箱」的假容器。"""

    def __init__(self) -> None:
        self.executed: list[str] = []

    @property
    def id(self) -> str:
        return "counting"

    def exec(self, command: str, *, timeout: int) -> CommandResult:
        self.executed.append(command)
        return CommandResult(output=f"第 {len(self.executed)} 次", exit_code=0)


class BlockingContainer(CountingContainer):
    """直到测试放行才结束的假容器。"""

    def __init__(self) -> None:
        super().__init__()
        self.started = threading.Event()
        self.resume = threading.Event()

    def exec(self, command: str, *, timeout: int) -> CommandResult:
        del timeout
        self.started.set()
        self.resume.wait()
        return super().exec(command, timeout=1)


class CountingPool:
    def __init__(self, container: CountingContainer) -> None:
        self._container = container

    def current(self, thread_id: str) -> CountingContainer:
        return self._container

    async def discard(self, thread_id: str) -> None:
        """删会话竞态里不需要真容器，但必须走完 broker 的销毁契约。"""


class PausingCache:
    """把去重查询停在取得 workspace backend 之后。"""

    def __init__(self) -> None:
        self.queried = asyncio.Event()
        self.resume = asyncio.Event()

    async def get(self, thread_id: str, checkpoint_ns: str, shape: str) -> None:
        del thread_id, checkpoint_ns, shape
        self.queried.set()
        await self.resume.wait()

    async def put(
        self,
        thread_id: str,
        checkpoint_ns: str,
        shape: str,
        result: dict[str, object],
    ) -> None:
        del thread_id, checkpoint_ns, shape, result


class ResumeOnCompetingThreadLock:
    """删除请求尝试取 thread 锁时，放行暂停的写请求。

    修复前 write 没持锁，删除会先清目录，迟到 write 随后将它复活；
    修复后 write 已持锁，删除只能在 write 完成后清理。
    """

    def __init__(self, cache: PausingCache) -> None:
        self._cache = cache
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def hold(self, thread_id: str) -> AsyncIterator[None]:
        del thread_id
        if self._cache.queried.is_set():
            self._cache.resume.set()
        async with self._lock:
            yield


@pytest.fixture
def container() -> CountingContainer:
    return CountingContainer()


@pytest.fixture
def space(tmp_path: Path) -> Workspace:
    created = Workspace(root=tmp_path)
    created.create(THREAD)
    return created


@pytest.fixture
def client(space: Workspace, container: CountingContainer, live_cache: Redis, tmp_path: Path) -> httpx.AsyncClient:
    broker = Broker(
        workspace=space,
        pool=CountingPool(container),  # type: ignore[arg-type]
        skills=SkillStore(tmp_path / "skill"),
        cache=ToolCache(live_cache),
    )
    app = create_app(broker)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BROKER_URL)


async def _call(client: httpx.AsyncClient, tool: str, payload: dict[str, object]) -> dict[str, object]:
    response = await client.post(f"/threads/{THREAD}/tool/{tool}", json=payload)
    response.raise_for_status()
    parsed: dict[str, object] = response.json()
    return parsed


async def test_a_replayed_execute_does_not_reach_the_sandbox(
    client: httpx.AsyncClient, container: CountingContainer
) -> None:
    """步骤六验证②：命中缓存时不进沙箱 —— 数的就是容器里跑了几次。"""
    payload: dict[str, object] = {"command": "echo 一", "checkpoint_ns": NS}

    first = await _call(client, "execute", payload)
    second = await _call(client, "execute", payload)

    assert container.executed == ["echo 一"]
    assert first == second


async def test_a_different_call_still_reaches_the_sandbox(
    client: httpx.AsyncClient, container: CountingContainer
) -> None:
    """去重不能把同一轮里的另一个调用也挡住 —— 它们的 ns 不同。"""
    await _call(client, "execute", {"command": "echo 一", "checkpoint_ns": NS})
    await _call(client, "execute", {"command": "echo 二", "checkpoint_ns": "tools:3ad455cb"})

    assert container.executed == ["echo 一", "echo 二"]


async def test_a_call_without_a_key_is_never_deduplicated(
    client: httpx.AsyncClient, container: CountingContainer
) -> None:
    """图之外调用时拿不到 ns。少一层去重只是回到没有它的从前，不该报错。"""
    await _call(client, "execute", {"command": "echo 一"})
    await _call(client, "execute", {"command": "echo 一"})

    assert len(container.executed) == 2


async def test_a_replayed_delete_returns_the_first_result_not_an_error(
    client: httpx.AsyncClient, space: Workspace
) -> None:
    """**这是幂等键真正要解决的那一幕。**

    首次删除成功；重放时文件已经没了，真去执行会返回一个首次执行时没有的错误，
    而 LLM 会据此改变后续行为。命中缓存则原样还回第一次的结果。
    """
    (space.lookup(THREAD) / "old.csv").write_text("a,b\n", encoding="utf-8")
    payload: dict[str, object] = {"file_path": "/workspace/old.csv", "checkpoint_ns": NS}

    first = await _call(client, "delete", payload)
    second = await _call(client, "delete", payload)

    assert first["error"] is None
    assert second == first


async def test_a_replayed_edit_returns_the_first_result_not_an_error(
    client: httpx.AsyncClient, space: Workspace
) -> None:
    """同上：重放时 `old_string` 已经被换掉了，真去执行会报「找不到」。"""
    (space.lookup(THREAD) / "note.txt").write_text("旧的", encoding="utf-8")
    payload: dict[str, object] = {
        "file_path": "/workspace/note.txt",
        "old_string": "旧的",
        "new_string": "新的",
        "checkpoint_ns": NS,
    }

    first = await _call(client, "edit", payload)
    second = await _call(client, "edit", payload)

    assert first["error"] is None
    assert second == first


async def test_a_replayed_write_returns_the_first_result(client: httpx.AsyncClient) -> None:
    payload: dict[str, object] = {"file_path": "/workspace/a.txt", "content": "一", "checkpoint_ns": NS}

    first = await _call(client, "write", payload)
    second = await _call(client, "write", payload)

    assert second == first


async def test_a_late_write_cannot_recreate_a_purged_workspace(
    space: Workspace,
    container: CountingContainer,
    tmp_path: Path,
) -> None:
    """tool/write 必须与 thread purge 共用同一把生命周期锁。"""
    cache = PausingCache()
    broker = Broker(
        workspace=space,
        pool=CountingPool(container),  # type: ignore[arg-type]
        skills=SkillStore(tmp_path / "skill-race"),
        cache=cache,  # type: ignore[arg-type]
        _thread_locks=ResumeOnCompetingThreadLock(cache),  # type: ignore[arg-type]
    )
    writing = asyncio.create_task(
        tool_write(
            THREAD,
            WriteRequest(file_path="/workspace/reborn.txt", content="迟到写入", checkpoint_ns=NS),
            broker,
        )
    )
    await asyncio.wait_for(cache.queried.wait(), timeout=1)

    await destroy_thread(THREAD, broker)
    written = await writing

    assert written.error is None
    assert space.exists(THREAD) is False


async def test_a_cancelled_execute_keeps_purge_waiting_for_the_container(
    space: Workspace,
    tmp_path: Path,
) -> None:
    """请求取消不能让 purge 越过仍在运行的容器命令。"""
    container = BlockingContainer()
    broker = Broker(
        workspace=space,
        pool=CountingPool(container),  # type: ignore[arg-type]
        skills=SkillStore(tmp_path / "skill-cancel"),
    )
    executing = asyncio.create_task(tool_execute(THREAD, ExecuteRequest(command="echo 慢命令"), broker))
    started = await asyncio.to_thread(container.started.wait, 1)
    assert started

    executing.cancel()
    purging = asyncio.create_task(destroy_thread(THREAD, broker))
    purge_waited = False
    try:
        await asyncio.wait_for(asyncio.shield(purging), timeout=0.05)
    except TimeoutError:
        purge_waited = True
    finally:
        container.resume.set()
        with suppress(asyncio.CancelledError):
            await executing
        await purging

    assert purge_waited
    assert space.exists(THREAD) is False


def test_file_chunks_close_the_open_file_when_streaming_stops() -> None:
    """客户端断开时响应后台任务不一定执行，迭代器自己必须关 fd。"""
    chunk_size = 64 * 1024
    opened = io.BytesIO(b"a" * (chunk_size + 1))
    chunks = _file_chunks(opened)

    assert len(next(chunks)) == chunk_size
    chunks.close()

    assert opened.closed


async def test_file_response_closes_before_body_streaming_starts(
    space: Workspace,
    container: CountingContainer,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """响应头发送时就断开，正文迭代器还没启动，响应层也必须关 fd。"""
    target = space.lookup(THREAD) / "stream.bin"
    target.write_bytes(b"stream")
    opened = target.open("rb")

    def reuse_opened(path: Path, *args: object, **kwargs: object) -> BinaryIO:
        del path, args, kwargs
        return opened

    monkeypatch.setattr(Path, "open", reuse_opened)
    broker = Broker(
        workspace=space,
        pool=CountingPool(container),  # type: ignore[arg-type]
        skills=SkillStore(tmp_path / "skill-stream"),
    )
    response = await workspace_file(THREAD, broker, path="stream.bin")
    scope: Scope = {"type": "http", "asgi": {"spec_version": "2.4"}}

    async def receive() -> Message:
        return {"type": "http.disconnect"}

    async def disconnect_on_start(message: Message) -> None:
        del message
        raise OSError("client disconnected")

    try:
        with pytest.raises(ClientDisconnect):
            await response(scope, receive, disconnect_on_start)
        assert opened.closed
    finally:
        opened.close()


@pytest.mark.parametrize(
    ("tool", "payload"),
    [
        ("ls", {"path": "/workspace"}),
        ("read", {"file_path": "/workspace/read.txt"}),
        ("glob", {"pattern": "*.txt"}),
        ("grep", {"pattern": "内容"}),
    ],
)
async def test_read_only_tools_are_not_deduplicated(
    client: httpx.AsyncClient, space: Workspace, tool: str, payload: dict[str, object]
) -> None:
    """步骤六验证③：纯读工具不去重。

    它们没有副作用，重放一次得到的就是当时该得到的东西；缓存反而会把
    「文件后来变了」这件事藏起来。
    """
    target = space.lookup(THREAD) / "read.txt"
    target.write_text("内容一", encoding="utf-8")
    keyed = payload | {"checkpoint_ns": NS}

    await _call(client, tool, keyed)
    target.write_text("内容二", encoding="utf-8")
    after = await _call(client, tool, keyed)

    assert "内容一" not in str(after)


async def test_a_broker_without_a_cache_still_works(
    space: Workspace, container: CountingContainer, tmp_path: Path
) -> None:
    """没配 Redis 时去重整个关掉 —— 那只是回到没有它的从前，不该让 broker 起不来。"""
    app = create_app(
        Broker(
            workspace=space,
            pool=CountingPool(container),  # type: ignore[arg-type]
            skills=SkillStore(tmp_path / "skill"),
        )
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BROKER_URL) as bare:
        await _call(bare, "execute", {"command": "echo 一", "checkpoint_ns": NS})
        await _call(bare, "execute", {"command": "echo 一", "checkpoint_ns": NS})

    assert len(container.executed) == 2


async def test_the_thread_is_part_of_the_key(
    client: httpx.AsyncClient, container: CountingContainer, space: Workspace
) -> None:
    """两个会话的 ns 撞上了也不能互相看见对方的结果。"""
    await _call(client, "execute", {"command": "echo 一", "checkpoint_ns": NS})
    another_thread = uuid4().hex
    space.create(another_thread)

    response = await client.post(
        f"/threads/{another_thread}/tool/execute", json={"command": "echo 一", "checkpoint_ns": NS}
    )
    response.raise_for_status()

    assert len(container.executed) == 2


async def test_a_reply_lost_after_execution_does_not_re_execute(
    client: httpx.AsyncClient, container: CountingContainer
) -> None:
    """**定点注入的那一刀**：沙箱已经跑完、结果也已记下，回程的响应丢了。

    worker 被 kill -9 之后由另一个副本重放同一次调用 —— 这一次必须命中缓存，
    否则那段代码就跑了两遍（LLM 生成的代码可能追加写、累加计数、删文件）。

    **残留风险按 ADR-0014 登记在案**：若崩溃发生在沙箱**执行途中**（结果还没记下），
    这条缓存里什么都没有，重放仍会真跑一次。那需要额外记一个 `started` 标记才认得出来，
    本期不做。
    """
    payload: dict[str, object] = {"command": "echo 累加", "checkpoint_ns": NS}
    await _call(client, "execute", payload)

    # worker 那一侧从此什么都没收到 —— 重放的是同一个 (thread_id, checkpoint_ns)
    replayed = await _call(client, "execute", payload)

    assert container.executed == ["echo 累加"]
    assert replayed["output"] == "第 1 次"
