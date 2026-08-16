"""broker 的测试：8 个工具经 HTTP 全部走通，排队排位能跨进程推回来。

**起一个真的 uvicorn**，不用 ASGI 传输：backend 是同步客户端（框架的工具调用本就
跑在工作线程里），而 ASGI 传输是纯异步的，顶替掉这一段就等于没验传输层 ——
而传输层正是本步骤唯一改动的东西。

不起 Docker：容器由假池提供，这里验的是 broker 的接线，不是 Docker。
"""

import asyncio
import socket
import threading
import time
from base64 import b64encode
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
import uvicorn
from deepagents.backends.protocol import ExecuteResponse, LsResult

from broker.app import create_app
from broker.runtime import AbsentContainer, Broker
from broker.skill import SkillStore
from sandbox.container import CommandResult
from sandbox.path import PathEscapeError
from sandbox.pool import PoolStat, QueuePositionCallback, SandboxQueueTimeoutError
from sandbox.remote import (
    BrokerConnection,
    FileMissingError,
    RemoteSandboxBackend,
    RemoteSandboxPool,
    RemoteWorkspace,
)
from sandbox.workspace import Workspace

THREAD = "thread-1"
# 租约的持有者。生产里取的是 run 标识 —— 崩溃恢复接着跑的是同一个 run
HOLDER = "run-1"


class FakeContainer:
    def __init__(self) -> None:
        self.ran: list[str] = []

    @property
    def id(self) -> str:
        return "fake-container"

    def exec(self, command: str, *, timeout: int) -> CommandResult:
        self.ran.append(command)
        return CommandResult(output=f"跑过了：{command}", exit_code=0)


# 假池的容量，判据只看「不是 0」与「真实反映占用」
FAKE_CAPACITY = 20


class FakePool:
    """可以被要求排队、超时或直接给容器的假池。"""

    def __init__(self) -> None:
        self.held: dict[str, FakeContainer] = {}
        self.released: list[str] = []
        self.discarded: list[str] = []
        self.queue_position: list[int] = []
        self.fail_with: Exception | None = None
        self.container_gone = False

    async def acquire(
        self, thread_id: str, *, holder: str, on_queued: QueuePositionCallback | None = None
    ) -> FakeContainer:
        for position in self.queue_position:
            if on_queued is not None:
                on_queued(position)
            await asyncio.sleep(0)
        if self.fail_with is not None:
            raise self.fail_with
        return self.held.setdefault(thread_id, FakeContainer())

    async def release(self, thread_id: str, *, holder: str) -> None:
        self.released.append(thread_id)

    async def discard(self, thread_id: str) -> None:
        self.discarded.append(thread_id)
        self.held.pop(thread_id, None)

    def current(self, thread_id: str) -> FakeContainer | None:
        return None if self.container_gone else self.held.get(thread_id)

    def stat(self) -> PoolStat:
        return PoolStat(in_use=len(self.held), capacity=FAKE_CAPACITY, queued=0)


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port


@pytest.fixture
def pool() -> FakePool:
    return FakePool()


@pytest.fixture
def space(tmp_path: Path) -> Workspace:
    return Workspace(root=tmp_path)


@pytest.fixture
def broker_url(space: Workspace, pool: FakePool, tmp_path: Path) -> Iterator[str]:
    """在一个空闲端口上把 broker 真的跑起来。"""
    port = _free_port()
    app = create_app(Broker(workspace=space, pool=pool, skills=SkillStore(tmp_path / "skill")))  # type: ignore[arg-type]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    if not server.started:
        pytest.fail("broker 没能在 10 秒内起来")

    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@pytest.fixture
def backend(broker_url: str, space: Workspace) -> RemoteSandboxBackend:
    space.path(THREAD)
    return RemoteSandboxBackend(THREAD, base_url=broker_url)


@pytest.fixture
def connection(broker_url: str) -> Iterator[BrokerConnection]:
    opened = BrokerConnection(base_url=broker_url)
    yield opened


# ------------------------------------------------------------------ Skill 仓库与物化
async def test_skill_storage_and_full_alignment_cross_the_http_boundary(
    connection: BrokerConnection, space: Workspace
) -> None:
    skill_id = "11111111-1111-1111-1111-111111111111"
    name = "annualized-naming"
    original = b"---\nname: annualized-naming\ndescription: annualized naming\n---\n"
    await connection.call(
        "POST",
        f"/skill/{skill_id}/versions/1",
        json={
            "files": [
                {"path": "SKILL.md", "content": b64encode(original).decode()},
                {"path": "notes/rule.txt", "content": b64encode(b"252 days").decode()},
            ]
        },
    )
    thread_id = await RemoteWorkspace(connection).create(uuid4().hex)
    payload = {"skills": [{"skill_id": skill_id, "version": 1, "name": name}]}

    await connection.call("POST", f"/threads/{thread_id}/skill/align", json=payload)
    skill_root = space.path(thread_id) / "skill"
    target = skill_root / name / "SKILL.md"
    target.write_bytes(b"broken")
    extra = skill_root / "invented" / "nested" / "extra.txt"
    extra.parent.mkdir(parents=True)
    extra.write_bytes(b"extra")
    await connection.call("POST", f"/threads/{thread_id}/skill/align", json=payload)

    assert target.read_bytes() == original
    assert (skill_root / name / "notes" / "rule.txt").read_bytes() == b"252 days"
    assert not (skill_root / "invented").exists()


# ------------------------------------------------------------------ 八个工具
def test_results_come_back_as_objects_not_dicts(backend: RemoteSandboxBackend) -> None:
    """Agent 侧读的是 `result.error` 这样的属性。

    把 JSON 原样传回去，类型检查看不出来，而 agent 第一次读字段就 AttributeError。
    """
    backend.write("/workspace/one.txt", "x")

    assert isinstance(backend.ls("/workspace"), LsResult)
    assert isinstance(backend.execute("echo hi"), ExecuteResponse)


def test_write_then_read_round_trips(backend: RemoteSandboxBackend) -> None:
    backend.write("/workspace/data.csv", "a,b\n1,2\n")

    result = backend.read("/workspace/data.csv")

    assert result.error is None
    assert result.file_data is not None


def test_ls_lists_what_was_written(backend: RemoteSandboxBackend) -> None:
    backend.write("/workspace/one.txt", "x")

    result = backend.ls("/workspace")

    assert result.error is None
    assert any("one.txt" in str(entry) for entry in result.entries or [])


def test_paths_come_back_in_the_agent_view(backend: RemoteSandboxBackend) -> None:
    """翻译发生在 broker 侧。回来的路径少了 /workspace 前缀，agent 拿它再读就会越界。"""
    backend.write("/workspace/one.txt", "x")

    result = backend.glob("*.txt")

    assert [entry["path"] for entry in result.matches or []] == ["/workspace/one.txt"]


def test_edit_replaces_in_place(backend: RemoteSandboxBackend) -> None:
    backend.write("/workspace/one.txt", "旧的")

    backend.edit("/workspace/one.txt", "旧的", "新的")

    assert "新的" in str(backend.read("/workspace/one.txt").file_data)


def test_delete_removes_the_file(backend: RemoteSandboxBackend) -> None:
    backend.write("/workspace/one.txt", "x")

    backend.delete("/workspace/one.txt")

    assert backend.read("/workspace/one.txt").error is not None


def test_grep_finds_the_literal(backend: RemoteSandboxBackend) -> None:
    backend.write("/workspace/one.txt", "年化波动率\n别的\n")

    result = backend.grep("年化波动率")

    assert result.error is None
    assert result.matches


def test_a_path_outside_the_workspace_comes_back_as_an_error(backend: RemoteSandboxBackend) -> None:
    """越界要变成工具的 error 字段。抛异常会让整个 run 失败，而 LLM 本可以自己改路径。"""
    result = backend.read("/etc/passwd")

    assert result.error is not None


def test_execute_reaches_the_container(backend: RemoteSandboxBackend, pool: FakePool) -> None:
    pool.held[THREAD] = FakeContainer()

    result = backend.execute("python analysis.py")

    assert result.exit_code == 0
    assert "python analysis.py" in result.output


def test_execute_without_a_container_returns_an_error_not_an_exception(backend: RemoteSandboxBackend) -> None:
    """容器被回收之后 execute 只能失败，但失败要以返回值的形式回给 LLM。"""
    result = backend.execute("echo hi")

    assert result.exit_code != 0
    assert "沙箱" in result.output


def test_file_tools_work_when_the_container_is_gone(backend: RemoteSandboxBackend, pool: FakePool) -> None:
    """七个文件工具直接读写宿主目录 —— 容器回收后翻看历史文件不该要冷启动一个容器。"""
    backend.write("/workspace/kept.txt", "还在")
    pool.container_gone = True

    assert backend.read("/workspace/kept.txt").error is None
    assert backend.ls("/workspace").error is None


def test_upload_and_download_round_trip_bytes(backend: RemoteSandboxBackend) -> None:
    """产物多半是图片，字节接口不能被当成文本处理。"""
    payload = b"\x89PNG\r\n\x1a\n binary"

    backend.upload_files([("/workspace/chart.png", payload)])
    found = backend.download_files(["/workspace/chart.png"])

    assert found[0].content == payload
    assert found[0].error is None


# ------------------------------------------------------------------ 排队排位


def written(path: Path, content: bytes) -> Path:
    """写一个文件，目录不存在就先建。

    真实里 `outputs/` 由沙箱自己建 —— broker 进程在容器里是 root，它建出来的目录
    以宿主用户跑的沙箱写不进去。用例在这里替沙箱做这一步。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


async def test_queue_positions_stream_back_before_ready(connection: BrokerConnection, pool: FakePool) -> None:
    """排位靠流式响应跨进程推回来，不轮询。少了它教师会盯着一个不动的界面等几分钟。"""
    pool.queue_position = [3, 2, 1]
    seen: list[int] = []

    async def record(position: int) -> None:
        seen.append(position)

    await RemoteSandboxPool(connection).acquire(THREAD, holder=HOLDER, on_queued=record)

    assert seen == [3, 2, 1]
    await connection.aclose()


async def test_no_position_is_reported_when_a_sandbox_is_free(connection: BrokerConnection, pool: FakePool) -> None:
    seen: list[int] = []

    async def record(position: int) -> None:
        seen.append(position)

    await RemoteSandboxPool(connection).acquire(THREAD, holder=HOLDER, on_queued=record)

    assert seen == []
    await connection.aclose()


async def test_a_queue_timeout_survives_the_hop(connection: BrokerConnection, pool: FakePool) -> None:
    """排队超时要在 api 侧还原成同一个异常，否则 run.failed 的 retryable 会判错。"""
    pool.fail_with = SandboxQueueTimeoutError("等待沙箱超过 600 秒")

    with pytest.raises(SandboxQueueTimeoutError):
        await RemoteSandboxPool(connection).acquire(THREAD, holder=HOLDER)

    await connection.aclose()


async def test_releasing_reaches_the_pool(connection: BrokerConnection, pool: FakePool) -> None:
    await RemoteSandboxPool(connection).release(THREAD, holder=HOLDER)

    assert pool.released == [THREAD]
    await connection.aclose()


# ------------------------------------------------------------------ 会话目录
async def test_a_created_thread_gets_a_directory(connection: BrokerConnection, space: Workspace) -> None:
    thread_id = await RemoteWorkspace(connection).create(uuid4().hex)

    assert space.exists(thread_id)
    await connection.aclose()


async def test_a_saved_file_lands_in_the_workspace(connection: BrokerConnection, space: Workspace) -> None:
    workspace = RemoteWorkspace(connection)
    thread_id = await workspace.create(uuid4().hex)

    await workspace.save(thread_id, "holdings.csv", b"a,b\n")

    assert (space.path(thread_id) / "holdings.csv").read_bytes() == b"a,b\n"
    await connection.aclose()


# ------------------------------------------------------------------ 工作目录的浏览
async def test_the_tree_reaches_across_the_hop(connection: BrokerConnection, space: Workspace) -> None:
    workspace = RemoteWorkspace(connection)
    thread_id = await workspace.create(uuid4().hex)
    written(space.path(thread_id) / "outputs" / "chart.png", b"png")
    (space.path(thread_id) / "analyze.py").write_text("print(1)\n", encoding="utf-8")

    found = await workspace.tree(thread_id)

    assert [one.path for one in found.entries] == ["analyze.py", "outputs", "outputs/chart.png"]
    assert not found.truncated
    await connection.aclose()


async def test_a_preview_comes_back_as_text(connection: BrokerConnection, space: Workspace) -> None:
    workspace = RemoteWorkspace(connection)
    thread_id = await workspace.create(uuid4().hex)
    (space.path(thread_id) / "analyze.py").write_text("一\n二\n三\n", encoding="utf-8")

    found = await workspace.preview(thread_id, "analyze.py", offset=1, limit=1)

    assert found.text == "二"
    assert (found.total_line, found.start_line, found.end_line) == (3, 2, 2)
    await connection.aclose()


async def test_previewing_a_binary_file_is_flagged_not_garbled(connection: BrokerConnection, space: Workspace) -> None:
    workspace = RemoteWorkspace(connection)
    thread_id = await workspace.create(uuid4().hex)
    written(space.path(thread_id) / "outputs" / "chart.png", b"\x89PNG\x00\x01")

    found = await workspace.preview(thread_id, "outputs/chart.png", offset=0, limit=10)

    assert found.is_binary
    await connection.aclose()


async def test_a_workspace_file_streams_back_whole(connection: BrokerConnection, space: Workspace) -> None:
    workspace = RemoteWorkspace(connection)
    thread_id = await workspace.create(uuid4().hex)
    (space.path(thread_id) / "holdings.csv").write_bytes(b"a,b\n" * 1000)

    opened = await workspace.open(thread_id, "holdings.csv")

    assert b"".join([chunk async for chunk in opened.chunk]) == b"a,b\n" * 1000
    assert opened.size == 4000
    await connection.aclose()


async def test_an_opened_file_carries_its_content_type(connection: BrokerConnection, space: Workspace) -> None:
    """前端拿它决定是塞进 <img> 还是当文本读。"""
    workspace = RemoteWorkspace(connection)
    thread_id = await workspace.create(uuid4().hex)
    written(space.path(thread_id) / "outputs" / "chart.png", b"png")

    opened = await workspace.open(thread_id, "outputs/chart.png")

    assert opened.mime == "image/png"
    await connection.aclose()


async def test_stat_gives_back_a_normalized_path(connection: BrokerConnection, space: Workspace) -> None:
    """这个路径要拿去拼 nginx 的内部跳转，因此它必须已经规范化。

    把 `./` 这类原样交给 nginx，等于把「这个路径指向哪里」的解释权让给它 ——
    而它的解析规则与这一侧的越界判定不是同一套。
    """
    workspace = RemoteWorkspace(connection)
    thread_id = await workspace.create(uuid4().hex)
    written(space.path(thread_id) / "outputs" / "chart.png", b"png-bytes")

    found = await workspace.stat(thread_id, "outputs/./chart.png")

    assert found.path == "outputs/chart.png"
    assert found.size == len(b"png-bytes")
    assert found.mime == "image/png"
    await connection.aclose()


@pytest.mark.parametrize("relative", ["never-made.csv", "../../etc/passwd"])
async def test_a_missing_or_escaping_path_reads_as_missing(connection: BrokerConnection, relative: str) -> None:
    """越界与不存在给同一个回答，否则这个端点就成了探测宿主机文件的工具。"""
    workspace = RemoteWorkspace(connection)
    thread_id = await workspace.create(uuid4().hex)

    with pytest.raises(FileMissingError):
        await workspace.open(thread_id, relative)
    await connection.aclose()


@pytest.mark.parametrize("relative", ["never-made.csv", "../../etc/passwd"])
async def test_stat_of_a_missing_or_escaping_path_reads_as_missing(connection: BrokerConnection, relative: str) -> None:
    """与取字节那条同一个规矩 —— 探测不到「哪些路径存在」。"""
    workspace = RemoteWorkspace(connection)
    thread_id = await workspace.create(uuid4().hex)

    with pytest.raises(FileMissingError):
        await workspace.stat(thread_id, relative)
    await connection.aclose()


async def test_stat_of_a_directory_says_so(connection: BrokerConnection, space: Workspace) -> None:
    workspace = RemoteWorkspace(connection)
    thread_id = await workspace.create(uuid4().hex)
    (space.path(thread_id) / "outputs").mkdir()

    with pytest.raises(IsADirectoryError):
        await workspace.stat(thread_id, "outputs")
    await connection.aclose()


async def test_opening_a_directory_says_so(connection: BrokerConnection, space: Workspace) -> None:
    """目录在树里看得见，说出来不泄露任何东西。"""
    workspace = RemoteWorkspace(connection)
    thread_id = await workspace.create(uuid4().hex)
    (space.path(thread_id) / "outputs").mkdir()

    with pytest.raises(IsADirectoryError):
        await workspace.preview(thread_id, "outputs", offset=0, limit=10)
    await connection.aclose()


async def test_removing_a_file_takes_it_off_disk(connection: BrokerConnection, space: Workspace) -> None:
    workspace = RemoteWorkspace(connection)
    thread_id = await workspace.create(uuid4().hex)
    await workspace.save(thread_id, "holdings.csv", b"a,b\n")

    await workspace.remove(thread_id, "holdings.csv")

    assert not (space.path(thread_id) / "holdings.csv").exists()
    await connection.aclose()


async def test_removing_a_directory_is_refused(connection: BrokerConnection, space: Workspace) -> None:
    workspace = RemoteWorkspace(connection)
    thread_id = await workspace.create(uuid4().hex)
    (space.path(thread_id) / "outputs").mkdir()

    with pytest.raises(IsADirectoryError):
        await workspace.remove(thread_id, "outputs")
    await connection.aclose()


async def test_a_file_can_be_saved_into_a_subdirectory(connection: BrokerConnection, space: Workspace) -> None:
    workspace = RemoteWorkspace(connection)
    thread_id = await workspace.create(uuid4().hex)
    (space.path(thread_id) / "data").mkdir()

    saved = await workspace.save(thread_id, "holdings.csv", b"a,b\n", directory="data")

    assert saved == "data/holdings.csv"
    assert (space.path(thread_id) / "data" / "holdings.csv").read_bytes() == b"a,b\n"
    await connection.aclose()


async def test_saving_into_a_directory_that_is_not_there_is_refused(connection: BrokerConnection) -> None:
    workspace = RemoteWorkspace(connection)
    thread_id = await workspace.create(uuid4().hex)

    with pytest.raises(PathEscapeError):
        await workspace.save(thread_id, "holdings.csv", b"x", directory="never-made")
    await connection.aclose()


# ------------------------------------------------------------------ 没有容器时
def test_absent_container_refuses_to_execute() -> None:
    with pytest.raises(Exception, match="没有运行中的沙箱"):
        AbsentContainer().exec("echo hi", timeout=1)


def test_the_idempotency_key_is_accepted_even_though_p1_ignores_it(broker_url: str, space: Workspace) -> None:
    """P3 的去重要落在 broker 侧。本期不实现，但参数位现在就得留出来，否则那时要改协议。"""
    space.path(THREAD)
    response = httpx.post(
        f"{broker_url}/threads/{THREAD}/tool/write",
        json={"file_path": "/workspace/one.txt", "content": "x", "checkpoint_ns": "step:1"},
    )

    assert response.status_code == httpx.codes.OK


async def test_destroying_a_thread_removes_its_directory_and_container(
    connection: BrokerConnection, space: Workspace, pool: FakePool
) -> None:
    """删会话把两样东西一起收走：容器与整个工作目录。"""
    workspace = RemoteWorkspace(connection)
    thread_id = await workspace.create(uuid4().hex)
    await workspace.save(thread_id, "holdings.csv", b"a,b\n")

    await workspace.destroy(thread_id)

    assert space.exists(thread_id) is False
    assert pool.discarded == [thread_id]
    await connection.aclose()


async def test_destroying_a_thread_that_was_never_created_is_not_an_error(
    connection: BrokerConnection,
) -> None:
    """Api 那边的行已经没了，这里再报 404 只会让一次正常的删除看起来失败了。"""
    await RemoteWorkspace(connection).destroy(uuid4().hex)

    await connection.aclose()
