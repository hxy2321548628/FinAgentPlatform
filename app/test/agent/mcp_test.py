"""把 P10 §2 那几处离线跑得动的实测钉进门禁。

**这一层测的不是平台代码，是适配器与传输层的真实行为。** 装配层的三处定案
（平台自己压超时、逐个 server 各要各的、撞名剔除）都是从这几条实测推出来的 ——
库换个版本把行为改了，这里必须先红，否则那三处定案会安静地失去理由。

夹具是 `deploy/test/mcp/server.py`，按子进程起在临时端口上，与验收脚本起它的方式
一致。开发机的 `ALL_PROXY=socks://…` 会让 httpx 连不上 127.0.0.1（它不认 socks
方案），因此起夹具与连夹具两侧都把代理变量剥掉。
"""

import asyncio
import contextlib
import logging
import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from langchain_core.messages import ToolMessage
from langchain_core.tools import StructuredTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.interceptors import MCPToolCallRequest, MCPToolCallResult
from langchain_mcp_adapters.sessions import StreamableHttpConnection

from agent.circuit import McpCircuit
from agent.config import McpReference
from agent.mcp import RESERVED_TOOL_NAME, McpTarget, _CallGuard, load_mcp_tools, probe_mcp_server

FIXTURE_SCRIPT = Path(__file__).resolve().parents[3] / "deploy" / "test" / "mcp" / "server.py"

# 夹具起不来时等多久放弃。它只是个本地 uvicorn，正常两秒内就绪
FIXTURE_READY_SECOND = 20.0

# 平台压在 get_tools 外面的那道超时，在这几条用例里取小值 —— 验的是「哪一道先生效」，
# 不是那个具体秒数
PROBE_TIMEOUT_SECOND = 1.0

# 故意给 connection 一个大得离谱的值：外层超时必须仍然赢。**这正是 §2 第 2 条**——
# 真实默认是 sse_read_timeout=300，一个不回应的服务能把一次分析挂住五分钟
UNREACHABLE_CONNECTION_TIMEOUT_SECOND = 600.0

PROXY_VARIABLE = ("ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy")

FIXTURE_TOOL_NAME = {"search_paper", "slow_query", "read_file", "boom"}


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _clean_environment(port: int) -> dict[str, str]:
    environment = {name: value for name, value in os.environ.items() if name not in PROXY_VARIABLE}
    environment["MCP_FIXTURE_PORT"] = str(port)
    environment["NO_PROXY"] = "127.0.0.1,localhost"
    return environment


def _wait_until_serving(url: str, process: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + FIXTURE_READY_SECOND
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"夹具 MCP server 启动即退出：returncode={process.returncode}")
        with contextlib.suppress(httpx.HTTPError):
            # 405 就够了：它说明端口上跑着的确实是这个应用，而不是随便一个监听者
            httpx.head(url, timeout=1.0, trust_env=False)
            return
        time.sleep(0.2)
    raise RuntimeError(f"夹具 MCP server {FIXTURE_READY_SECOND} 秒内没起来：{url}")


@pytest.fixture(scope="module")
def fixture_url() -> Iterator[str]:
    """起一个夹具 MCP server，返回它的 streamable-http 地址。"""
    port = _free_port()
    url = f"http://127.0.0.1:{port}/mcp"
    process = subprocess.Popen(
        [sys.executable, str(FIXTURE_SCRIPT)],
        env=_clean_environment(port),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_until_serving(url, process)
        yield url
    finally:
        process.terminate()
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.wait(timeout=5)


@pytest.fixture
def hung_url() -> Iterator[str]:
    """一个接受连接、永不回应的地址。

    只 `listen` 不 `accept`：TCP 握手由内核在 backlog 里完成，客户端连得上、
    请求发得出去，然后一直等 —— 正是「服务卡住了」那种最难查的形态。
    """
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    try:
        yield f"http://127.0.0.1:{listener.getsockname()[1]}/mcp"
    finally:
        listener.close()


@pytest.fixture
def dead_url() -> str:
    """一个没人监听的地址，连接会当场被拒。"""
    return f"http://127.0.0.1:{_free_port()}/mcp"


@pytest.fixture(autouse=True)
def _direct_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in PROXY_VARIABLE:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")


def _connection(url: str, *, timeout: float | None = None) -> StreamableHttpConnection:
    connection = StreamableHttpConnection(url=url, transport="streamable_http")
    if timeout is not None:
        connection["timeout"] = timeout
        connection["sse_read_timeout"] = timeout
    return connection


async def test_the_adapter_only_produces_async_tools(fixture_url: str) -> None:
    """§2 第 5 条：适配器给的工具只有 `coroutine`，一次慢调用挂不住整个事件循环。

    F1 那句「你的服务慢 30 秒，全平台所有教师同时卡 30 秒」对 SSE / HTTP 不成立，
    而它正是取超时阈值时的依据 —— 这一条钉住的是那个更正。
    """
    client = MultiServerMCPClient({"fixture": _connection(fixture_url)})

    tools = await client.get_tools(server_name="fixture")

    assert {one.name for one in tools} == FIXTURE_TOOL_NAME
    structured = [one for one in tools if isinstance(one, StructuredTool)]
    assert len(structured) == len(tools)
    assert all(one.func is None for one in structured)
    assert all(one.coroutine is not None for one in structured)


async def test_one_dead_server_fails_the_whole_batch_but_not_a_per_server_load(fixture_url: str, dead_url: str) -> None:
    """§2 第 4 条：`get_tools()` 内部是 gather，一个连不上就整批抛。

    照官方示例写（一个 client 装所有 server、一次 `get_tools()`）的后果是：校外任意
    一台机器下线，所有挂了 MCP 的分析全都拿不到工具。装配层因此逐个 server 各要各的。
    """
    client = MultiServerMCPClient(
        {
            "fixture": _connection(fixture_url),
            "dead": _connection(dead_url),
        }
    )

    with pytest.raises(Exception) as together:
        await client.get_tools()
    assert isinstance(together.value, Exception)

    survived = await client.get_tools(server_name="fixture")
    assert {one.name for one in survived} == FIXTURE_TOOL_NAME


async def test_a_hung_server_is_cut_off_by_the_outer_timeout_and_leaves_the_loop_clean(
    hung_url: str, fixture_url: str
) -> None:
    """§2 第 2 与第 7 条：管住一个不回应的服务的是平台包在外面那道超时。

    connection 的 `timeout` 给到 600 秒也不影响结果 —— 掐断的是 `asyncio.timeout`。
    掐完之后同一个事件循环还能照常连别的服务，说明这条防线不留残渣。
    """
    client = MultiServerMCPClient({"hung": _connection(hung_url, timeout=UNREACHABLE_CONNECTION_TIMEOUT_SECOND)})

    started = time.monotonic()
    with pytest.raises(TimeoutError):
        async with asyncio.timeout(PROBE_TIMEOUT_SECOND):
            await client.get_tools(server_name="hung")
    elapsed = time.monotonic() - started

    assert elapsed < UNREACHABLE_CONNECTION_TIMEOUT_SECOND
    assert elapsed == pytest.approx(PROBE_TIMEOUT_SECOND, abs=2.0)

    healthy = MultiServerMCPClient({"fixture": _connection(fixture_url)})
    assert {one.name for one in await healthy.get_tools(server_name="fixture")} == FIXTURE_TOOL_NAME


async def test_a_tool_reporting_its_own_failure_comes_back_as_content(fixture_url: str) -> None:
    """§2 第 9 条：工具自己报错是一条正常返回，不是异常。

    这条是熔断口径的依据：传输层失败与「工具说它办不到」在调用侧长得完全不同，
    因此数得清 —— 只数前者。
    """
    client = MultiServerMCPClient({"fixture": _connection(fixture_url)})
    tools = {one.name: one for one in await client.get_tools(server_name="fixture")}

    result = await tools["boom"].ainvoke({"keyword": "沪深300"})

    assert "外部数据源暂时不可用" in str(result)


# ---------------------------------------------------------------------------
# 装配层：平台自己的代码
# ---------------------------------------------------------------------------


def target(
    url: str,
    *,
    name: str = "fixture",
    declared_tool_name: list[str] | None = None,
    enabled: bool = True,
    disabled_reason: str | None = None,
) -> McpTarget:
    return McpTarget(
        server_id=f"srv-{name}",
        name=name,
        url=url,
        transport="streamable_http",
        credential=None,
        declared_tool_name=sorted(FIXTURE_TOOL_NAME) if declared_tool_name is None else declared_tool_name,
        enabled=enabled,
        disabled_reason=disabled_reason,
    )


class Loader:
    def __init__(self, *targets: McpTarget) -> None:
        self._targets = {one.server_id: one for one in targets}
        self.calls: list[str] = []

    async def load_mcp_target(self, server_id: str) -> McpTarget | None:
        self.calls.append(server_id)
        return self._targets.get(server_id)


class Recorder:
    def __init__(self) -> None:
        self.failures: list[tuple[str, str]] = []
        self.successes: list[str] = []

    async def record_failure(self, server_id: str, *, reason: str) -> None:
        self.failures.append((server_id, reason))

    async def record_success(self, server_id: str) -> None:
        self.successes.append(server_id)


def reference(one: McpTarget) -> McpReference:
    return McpReference(server_id=one.server_id, name=one.name)


async def test_no_mcp_reference_touches_nothing_at_all() -> None:
    """不挂 MCP 的 run 必须一个额外动作都不做 —— 连一次目录查询都不该有。"""
    loader = Loader()

    assert await load_mcp_tools([], loader=loader) == []
    assert loader.calls == []


async def test_an_external_tool_cannot_take_over_the_builtin_read_file(fixture_url: str) -> None:
    """`P10④` 的单测形态：夹具提供一个叫 `read_file` 的工具，它必须被剔除。

    实测里外部工具不是「与内置的二选一」，而是**静默顶掉**内置那个 —— 一个上架时
    人畜无害的服务只要事后加一个同名工具，就能接管平台的文件读取。
    """
    one = target(fixture_url)
    loader = Loader(one)

    tools = await load_mcp_tools([reference(one)], loader=loader)

    names = {tool.name for tool in tools}
    assert "read_file" not in names
    assert names == FIXTURE_TOOL_NAME - RESERVED_TOOL_NAME


async def test_the_reserved_names_still_cover_every_builtin_file_tool() -> None:
    """撞名清单是硬编码的，这一条替它盯着上游 —— 加了第九个内置文件工具就红。"""
    from deepagents.middleware.filesystem import FilesystemMiddleware

    builtin = {tool.name for tool in FilesystemMiddleware(backend=None).tools}

    assert builtin <= RESERVED_TOOL_NAME


async def test_a_hung_server_does_not_drag_down_the_others(
    hung_url: str, fixture_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`P10③` 的单测形态：黑洞服务在平台设的秒数上被掐断，好的照常装上。

    **断言的是真实耗时**，不是「我们给 asyncio.timeout 传了 30」—— 后者验的是意图，
    框架换一种连接实现之后照样绿。
    """
    monkeypatch.setattr("agent.mcp.MCP_CONNECT_TIMEOUT", PROBE_TIMEOUT_SECOND)
    hung = target(hung_url, name="hung")
    good = target(fixture_url, name="fixture")
    loader, recorder = Loader(hung, good), Recorder()

    started = time.monotonic()
    tools = await load_mcp_tools([reference(hung), reference(good)], loader=loader, recorder=recorder)
    elapsed = time.monotonic() - started

    assert elapsed == pytest.approx(PROBE_TIMEOUT_SECOND, abs=2.0)
    assert {tool.name for tool in tools} == FIXTURE_TOOL_NAME - RESERVED_TOOL_NAME
    assert [server_id for server_id, _ in recorder.failures] == [hung.server_id]
    assert recorder.successes == [good.server_id]


async def test_a_dead_server_is_skipped_and_counted(dead_url: str, fixture_url: str) -> None:
    """连不上时抛的是 ExceptionGroup，宽类型才抓得住 —— 放过去会掀掉整次分析。"""
    dead = target(dead_url, name="dead")
    good = target(fixture_url, name="fixture")
    loader, recorder = Loader(dead, good), Recorder()

    tools = await load_mcp_tools([reference(dead), reference(good)], loader=loader, recorder=recorder)

    assert {tool.name for tool in tools} == FIXTURE_TOOL_NAME - RESERVED_TOOL_NAME
    assert [server_id for server_id, _ in recorder.failures] == [dead.server_id]


async def test_a_disabled_server_is_never_connected_to(fixture_url: str) -> None:
    """C4：已停用的一次都不连。连一次就等于把停用变成了「每次多等 30 秒」。"""
    one = target(fixture_url, enabled=False, disabled_reason="连续失败 5 次")
    loader, recorder = Loader(one), Recorder()

    tools = await load_mcp_tools([reference(one)], loader=loader, recorder=recorder)

    assert tools == []
    assert recorder.failures == []
    assert recorder.successes == []


async def test_a_snapshot_pointing_at_a_vanished_record_degrades(fixture_url: str) -> None:
    good = target(fixture_url)
    loader = Loader(good)

    tools = await load_mcp_tools([McpReference(server_id="srv-gone", name="gone"), reference(good)], loader=loader)

    assert {tool.name for tool in tools} == FIXTURE_TOOL_NAME - RESERVED_TOOL_NAME


async def test_a_stale_declared_tool_list_is_logged_not_enforced(
    fixture_url: str, caplog: pytest.LogCaptureFixture
) -> None:
    """清单过期是静默的，不比对就永远发现不了；但拦下来会打断一次正常的上游升级。"""
    one = target(fixture_url, declared_tool_name=["search_paper", "已经没有的工具"])
    loader = Loader(one)

    with caplog.at_level(logging.WARNING, logger="agent.mcp"):
        tools = await load_mcp_tools([reference(one)], loader=loader)

    assert {tool.name for tool in tools} == FIXTURE_TOOL_NAME - RESERVED_TOOL_NAME
    assert any("工具清单与上架时不一致" in one.getMessage() for one in caplog.records)


async def test_two_servers_offering_the_same_tool_keep_the_first(fixture_url: str) -> None:
    """两个外部服务同名工具时后一个会顶掉前一个，症状同样是「调了但结果不对」。"""
    first = target(fixture_url, name="first")
    second = target(fixture_url, name="second")
    loader = Loader(first, second)

    tools = await load_mcp_tools([reference(first), reference(second)], loader=loader)

    names = [tool.name for tool in tools]
    assert sorted(names) == sorted(FIXTURE_TOOL_NAME - RESERVED_TOOL_NAME)


async def test_a_slow_call_comes_back_as_an_error_result_instead_of_raising(
    fixture_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§2 第 3 条：抛出去的话，一次慢调用会掀掉一次已经跑了二十分钟的分析。"""
    monkeypatch.setattr("agent.mcp.MCP_CALL_TIMEOUT", PROBE_TIMEOUT_SECOND)
    one = target(fixture_url)
    tools = {tool.name: tool for tool in await load_mcp_tools([reference(one)], loader=Loader(one))}

    result = await tools["slow_query"].ainvoke(
        {"name": "slow_query", "args": {"keyword": "沪深300"}, "id": "call-1", "type": "tool_call"}
    )

    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert "调用超时" in str(result.content)


class FakeRedis:
    """够 `McpCircuit` 用的最小计数器。真 Redis 那一侧由 `circuit_test.py` 覆盖。"""

    def __init__(self) -> None:
        self.values: dict[str, int] = {}

    def pipeline(self) -> "FakeRedis":
        self._queued: list[str] = []
        return self

    def incr(self, key: str) -> None:
        self.values[key] = self.values.get(key, 0) + 1
        self._queued.append(key)

    def expire(self, key: str, second: int) -> None:
        return None

    async def execute(self) -> list[int]:
        return [self.values[key] for key in self._queued] + [1]

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)

    async def get(self, key: str) -> int | None:
        return self.values.get(key)


class Disabler:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def disable_for_failure(self, server_id: str, *, reason: str) -> bool:
        self.calls.append((server_id, reason))
        return True


def circuit_over(disabler: Disabler) -> McpCircuit:
    return McpCircuit(FakeRedis(), disabler, threshold=THREE_WAY_THRESHOLD)  # type: ignore[arg-type]


# 三条路各出一点，正好凑够它 —— 取 5 是为了与真实阈值同形
THREE_WAY_THRESHOLD = 5


async def test_all_three_entry_points_feed_the_same_counter(dead_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """§4.4：装配、单次调用、管理员探活必须共用一个计数器。

    **这一条堵的是判据自己会骗人的地方。** `P10⑤` 走的是探活那条路（免费且确定），
    而真实场景里失败大多来自装配与工具调用 —— 不共用的话，判据验的是一条没人走的路，
    **而它照样绿**。

    因此断言的不是「三处都调了同名函数」，而是**三处的失败累加到同一个数上**：
    两次装配 + 两次探活 + 一次调用超时，第五次才触发那一次停用。
    """
    monkeypatch.setattr("agent.mcp.MCP_CALL_TIMEOUT", PROBE_TIMEOUT_SECOND)
    dead = target(dead_url, name="dead")
    disabler = Disabler()
    circuit = circuit_over(disabler)

    # 入口一：装配
    await load_mcp_tools([reference(dead)], loader=Loader(dead), recorder=circuit)
    await load_mcp_tools([reference(dead)], loader=Loader(dead), recorder=circuit)
    # 入口二：管理员探活
    assert await probe_mcp_server(dead, recorder=circuit) is None
    assert await probe_mcp_server(dead, recorder=circuit) is None
    assert disabler.calls == [], "四次还不到阈值就停用，说明计数被谁多加了一次"

    # 入口三：单次工具调用超时。**记的是同一个 server_id**，因此这一次正好凑满
    result = await _CallGuard(server_id=dead.server_id, recorder=circuit)(
        MCPToolCallRequest(name="slow_query", args={"keyword": "沪深300"}, server_name="dead"),
        _never_answers,
    )

    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert [server_id for server_id, _ in disabler.calls] == [dead.server_id]
    assert f"连续失败 {THREE_WAY_THRESHOLD} 次" in disabler.calls[0][1]


async def _never_answers(request: MCPToolCallRequest) -> MCPToolCallResult:
    """一个永远不回话的 handler，让守卫真的跑一次超时而不是伪造它。"""
    await asyncio.sleep(PROBE_TIMEOUT_SECOND * 10)
    raise AssertionError("不该跑到这里")


async def test_a_disabled_server_can_still_be_probed(fixture_url: str) -> None:
    """探活正是管理员判断「它回来没有」的手段，对已停用的服务尤其要能连。"""
    one = target(fixture_url, enabled=False, disabled_reason="连续失败 5 次")

    found = await probe_mcp_server(one)

    assert found is not None
    assert set(found) == FIXTURE_TOOL_NAME


async def test_a_successful_probe_clears_the_count(fixture_url: str) -> None:
    """成功一次即清零 —— 一台恢复了的服务不该带着旧账继续走向停用。"""
    one = target(fixture_url)
    circuit = circuit_over(Disabler())
    for _ in range(THREE_WAY_THRESHOLD - 1):
        await circuit.record_failure(one.server_id, reason="连接失败")

    await probe_mcp_server(one, recorder=circuit)

    assert await circuit.failure_count(one.server_id) == 0
