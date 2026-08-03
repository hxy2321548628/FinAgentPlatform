"""API 测试共用的假运行时。

假的只有两样：**沙箱池**（不起 Docker）与**智能体**（不打模型 API）。
其余全是真的 —— 真的执行器、真的事件日志、真的 workspace，
否则验的就不是这一层与下面的衔接。
"""

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from deepagents.backends.protocol import BackendProtocol
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.app import create_app
from api.platform import Platform
from event.mapper import StreamChunk
from run.executor import RunExecutor
from run.log import EventLog
from sandbox.container import CommandResult
from sandbox.pool import QueuePositionCallback
from sandbox.workspace import Workspace


class FakeContainer:
    @property
    def id(self) -> str:
        return "fake-container"

    def exec(self, command: str, *, timeout: int) -> CommandResult:
        return CommandResult(output="", exit_code=0)


class FakePool:
    def __init__(self) -> None:
        self.released: list[str] = []

    async def acquire(self, thread_id: str, *, on_queued: QueuePositionCallback | None = None) -> FakeContainer:
        return FakeContainer()

    async def release(self, thread_id: str) -> None:
        self.released.append(thread_id)


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
def platform(pool: FakePool, space: Workspace, log: EventLog, agent: Agent) -> Platform:
    executor = RunExecutor(pool=pool, workspace=space, log=log, runner=agent)
    return Platform(workspace=space, pool=pool, log=log, executor=executor)  # type: ignore[arg-type]


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
