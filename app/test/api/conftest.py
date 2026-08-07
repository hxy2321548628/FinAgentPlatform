"""API 测试共用的假运行时。

**api 与 broker 之间走真的 HTTP**：broker 用 ASGI 传输在进程内跑起来，api 侧的
`RemoteWorkspace` / `RemoteSandboxPool` 照常发请求。拆分之后「建会话」「上传」
「取产物」全都跨了进程边界，用假对象顶掉这一段等于把要验的东西验没了。

假的只有两样：**沙箱池**（不起 Docker）与**智能体**（不打模型 API）。
其余全是真的 —— 真的执行器、真的事件日志、真的 workspace、真的 broker 路由。
"""

from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import cast

import httpx
import pytest
from deepagents.backends.protocol import BackendProtocol
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg_pool import AsyncConnectionPool
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from api.app import create_app
from api.platform import Platform
from broker.app import create_app as create_broker_app
from broker.runtime import Broker
from event.mapper import StreamChunk
from run.executor import RunExecutor
from run.log import EventLog
from sandbox.backend import SandboxBackend
from sandbox.container import CommandResult
from sandbox.pool import QueuePositionCallback
from sandbox.remote import BrokerConnection, RemoteBackendFactory, RemoteSandboxPool, RemoteWorkspace
from sandbox.workspace import Workspace
from store.checkpoint import CONNECTION_KWARGS, CheckpointPool
from store.postgres import create_engine
from store.redis import create_client

BROKER_URL = "http://broker.test"

# 这三样在这里都用不上：端点不读库，而 checkpointer 被假 agent 顶掉了。
# 给的是没连过的对象 —— 建它们不发起连接。真连上去验的部分在 test/store/，
# 那里连不上会 skip；换成真连接只会让两百多条与存储无关的用例一起停摆
UNUSED_DSN = "postgresql+psycopg://unused@127.0.0.1:1/unused"
UNUSED_CONNINFO = "postgresql://unused@127.0.0.1:1/unused"
UNUSED_REDIS_URL = "redis://127.0.0.1:1/0"


class FakeContainer:
    @property
    def id(self) -> str:
        return "fake-container"

    def exec(self, command: str, *, timeout: int) -> CommandResult:
        return CommandResult(output="", exit_code=0)


class FakePool:
    """broker 侧的假池：不起 Docker，但借还与查询的行为与真池一致。"""

    def __init__(self) -> None:
        self.released: list[str] = []
        self.held: dict[str, FakeContainer] = {}

    async def acquire(self, thread_id: str, *, on_queued: QueuePositionCallback | None = None) -> FakeContainer:
        container = self.held.setdefault(thread_id, FakeContainer())
        return container

    async def release(self, thread_id: str) -> None:
        self.released.append(thread_id)

    def current(self, thread_id: str) -> FakeContainer | None:
        return self.held.get(thread_id)


class Agent:
    """可以被逐个用例摆布的假智能体。"""

    def __init__(self) -> None:
        self.chunk: list[StreamChunk] = []
        self.side_effect: Exception | None = None
        self.asked: list[str] = []
        self.produce: dict[str, bytes] = {}

    def __call__(self, backend: BackendProtocol, thread_id: str, content: str) -> AsyncIterator[StreamChunk]:
        self.asked.append(content)

        async def stream() -> AsyncIterator[StreamChunk]:
            # 走字节接口：产物多半是图片，文本接口会在写 PNG 时就炸掉
            backend.upload_files([(f"/workspace/outputs/{name}", payload) for name, payload in self.produce.items()])
            for one in self.chunk:
                yield one
            if self.side_effect is not None:
                raise self.side_effect

        return stream()


@pytest.fixture
def agent() -> Agent:
    return Agent()


@pytest.fixture
def space(tmp_path: Path) -> Workspace:
    return Workspace(root=tmp_path)


@pytest.fixture
def log() -> EventLog:
    return EventLog()


@pytest.fixture
def pool() -> FakePool:
    return FakePool()


@pytest.fixture
def broker_app(space: Workspace, pool: FakePool) -> FastAPI:
    return create_broker_app(Broker(workspace=space, pool=pool))  # type: ignore[arg-type]


@pytest.fixture
def connection(broker_app: FastAPI) -> BrokerConnection:
    """到 broker 的连接，走 ASGI 传输 —— 真的 HTTP 语义，但不占端口。"""
    return BrokerConnection(
        base_url=BROKER_URL,
        client=httpx.AsyncClient(transport=httpx.ASGITransport(app=broker_app), base_url=BROKER_URL),
    )


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    created = create_engine(UNUSED_DSN, pool_size=1)
    yield created
    await created.dispose()


@pytest.fixture
async def cache() -> AsyncIterator[Redis]:
    created = create_client(UNUSED_REDIS_URL)
    yield created
    await created.aclose()


@pytest.fixture
async def checkpoint_pool() -> AsyncIterator[CheckpointPool]:
    created = cast(CheckpointPool, AsyncConnectionPool(conninfo=UNUSED_CONNINFO, kwargs=CONNECTION_KWARGS, open=False))
    yield created
    await created.close()


@pytest.fixture
def platform(
    connection: BrokerConnection,
    space: Workspace,
    pool: FakePool,
    log: EventLog,
    agent: Agent,
    engine: AsyncEngine,
    cache: Redis,
    checkpoint_pool: CheckpointPool,
) -> Platform:
    workspace = RemoteWorkspace(connection)
    remote_pool = RemoteSandboxPool(connection)

    # backend 是同步的，没法走 ASGI 传输（那是纯异步的）。这里换成本地实现直接读写
    # 同一个 tmp 目录 —— agent 侧看到的接口一模一样，而 broker 那边读到的是同一批文件，
    # 因此「产物由 broker 认领」这条链路仍然是真的
    def backend_factory(thread_id: str) -> SandboxBackend:
        return SandboxBackend(workspace=space.path(thread_id), container=pool.current(thread_id) or FakeContainer())

    executor = RunExecutor(
        pool=remote_pool, workspace=workspace, log=log, runner=agent, backend_factory=backend_factory
    )
    return Platform(
        workspace=workspace,
        pool=remote_pool,
        log=log,
        executor=executor,
        connection=connection,
        backend_factory=RemoteBackendFactory(base_url=BROKER_URL),
        engine=engine,
        cache=cache,
        checkpoint_pool=checkpoint_pool,
    )


@pytest.fixture
def api(platform: Platform) -> FastAPI:
    return create_app(platform)


@pytest.fixture
def client(api: FastAPI) -> Iterator[TestClient]:
    with TestClient(api) as opened:
        yield opened


def drain(client: TestClient, run_id: str) -> list[str]:
    """订阅到 run 结束，返回收到的每一行。

    执行是后台任务，提交那一刻它一行都还没跑 —— 想断言执行结果就得先等它跑完，
    而事件流本来就在 run 进终态时收尾，正好当同步点用。
    """
    with client.stream("GET", f"/api/runs/{run_id}/events") as response:
        return [line for line in response.iter_lines() if line]


@pytest.fixture
def thread_id(client: TestClient) -> str:
    response = client.post("/api/threads")
    identifier: str = response.json()["id"]
    return identifier
