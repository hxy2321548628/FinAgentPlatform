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
import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from langchain_core.tools import StructuredTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.sessions import StreamableHttpConnection

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
