"""API 测试共用的假运行时。

**api 与 broker 之间走真的 HTTP**：broker 用 ASGI 传输在进程内跑起来，api 侧的
`RemoteWorkspace` / `RemoteSandboxPool` 照常发请求。拆分之后「建会话」「上传」
「取产物」全都跨了进程边界，用假对象顶掉这一段等于把要验的东西验没了。

假的只有两样：**沙箱池**（不起 Docker）与**智能体**（不打模型 API）。
其余全是真的 —— 真的执行器、真的事件日志、真的 workspace、真的 broker 路由，
以及真的 Postgres 与 Redis：`GET /runs/{id}` 读的是 `runs` 表，事件流是 Stream，
拿假的顶掉就等于不验它们。库没起时这一整包会 skip。

**worker 与 api 恰好跑在同一个进程里，但中间仍然走真的队列**：`POST /runs` 只
`XADD`，事件是 worker 从 `XREADGROUP` 领走之后才写的。同进程只是省掉一次
`docker compose up`，投递与消费这条链路没有被绕过。
"""

import asyncio
from collections.abc import AsyncIterator, Iterator
from functools import partial
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from deepagents.backends.protocol import BackendProtocol
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.language_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from agent.config import AgentConfig
from api.app import create_app
from api.platform import Platform
from auth.password import PasswordHasher
from auth.session import DEFAULT_TTL_SECOND, SessionStore
from broker.app import create_app as create_broker_app
from broker.runtime import Broker
from broker.skill import SkillStore
from config import DEFAULT_UPLOAD_MAX_BYTE
from event.mapper import StreamChunk
from event.model import InterruptAction
from group.repository import Group, GroupRepository, JoinRequestRepository
from preset.repository import AgentRepository
from preset.review import ReviewRepository
from preset.skill import SkillRepository
from preset.skill_remote import RemoteSkillStore
from quota.policy import QuotaPolicy
from quota.rate import RateLimiter
from quota.usage import RunUsage
from run.cancel import CancelFlag
from run.executor import RunExecutor
from run.log import EventLog
from run.repository import RunRepository
from run.submitter import RunSubmitter
from sandbox.backend import SandboxBackend
from sandbox.container import CommandResult
from sandbox.pool import QueuePositionCallback
from sandbox.remote import BrokerConnection, RemoteBackendFactory, RemoteSandboxPool, RemoteWorkspace
from sandbox.workspace import Workspace
from task.queue import TaskQueue
from thread.repository import ThreadRepository
from thread.title import TitleWriter
from user.model import UserRole
from user.repository import User, UserRepository
from worker.loop import Worker

BROKER_URL = "http://broker.test"

TEST_CONSUMER = "test-worker"

# worker 的主循环靠它回到「该停了没」的判断上。默认 5 秒会让每条用例都多等一轮
TEST_BLOCK_MILLISECOND = 50

# 用例里登录用的口令。**哈希参数同时调到最低档**（见 `hasher`）——
# 默认档一次 64 MiB、几十毫秒，而这套用例每条都要登录一次
TEST_PASSWORD = "口令-test"

# 限流的窗口在用例里要大到不误伤：一条用例会发十几个请求，而窗口是按秒滑的。
# 真要验限流的那几条自己换一个更小的上限
TEST_RATE_LIMIT = 10_000
TEST_RATE_WINDOW_SECOND = 60

# 假 agent 被卡住时多久回头看一次「放行了没」
POLL_SECOND = 0.01

# 假模型给会话起的名字。真模型在 CI 里既没有凭据也不该花钱
FAKE_TITLE = "行业波动率分析"


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
        self.discarded: list[str] = []
        self.held: dict[str, FakeContainer] = {}

    async def acquire(
        self, thread_id: str, *, holder: str, on_queued: QueuePositionCallback | None = None
    ) -> FakeContainer:
        container = self.held.setdefault(thread_id, FakeContainer())
        return container

    async def release(self, thread_id: str, *, holder: str) -> None:
        self.released.append(thread_id)

    async def discard(self, thread_id: str) -> None:
        self.discarded.append(thread_id)
        self.held.pop(thread_id, None)

    def current(self, thread_id: str) -> FakeContainer | None:
        return self.held.get(thread_id)


class Agent:
    """可以被逐个用例摆布的假智能体。"""

    def __init__(self) -> None:
        self.chunk: list[StreamChunk] = []
        self.side_effect: Exception | None = None
        self.asked: list[str] = []
        self.produce: dict[str, bytes] = {}
        self.resumed: list[list[dict[str, object]]] = []
        self.configured: list[AgentConfig] = []
        self.pending_config: list[AgentConfig] = []
        # 下一次流结束后报告的待确认调用。**用完即清**：续跑那一次不该再停下来
        self.interrupt: list[InterruptAction] = []
        # 卡住不往下走，直到用例放行。**取消那几条用例非它不可**：假 agent 转眼就跑完，
        # 请求还没发出去 run 已经是终态了，验的就成了「取消一个已完成的 run」
        self.blocked = False

    def stream(
        self,
        backend: BackendProtocol,
        thread_id: str,
        content: str,
        agent_config: AgentConfig,
        *,
        user_id: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        self.asked.append(content)
        self.configured.append(agent_config)
        return self._stream(backend)

    def resume(
        self,
        backend: BackendProtocol,
        thread_id: str,
        decisions: list[dict[str, object]],
        agent_config: AgentConfig,
        *,
        user_id: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        self.resumed.append(decisions)
        self.configured.append(agent_config)
        return self._stream(backend)

    async def pending(
        self, backend: BackendProtocol, thread_id: str, agent_config: AgentConfig
    ) -> list[InterruptAction]:
        """下一次流结束后要不要停在等人确认上。用完即清 —— 续跑那一次就不该再停。"""
        self.pending_config.append(agent_config)
        waiting, self.interrupt = self.interrupt, []
        return waiting

    def _stream(self, backend: BackendProtocol) -> AsyncIterator[StreamChunk]:

        async def stream() -> AsyncIterator[StreamChunk]:
            while self.blocked:
                await asyncio.sleep(POLL_SECOND)
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
def log(live_cache: Redis) -> EventLog:
    return EventLog(live_cache)


@pytest.fixture
def pool() -> FakePool:
    return FakePool()


@pytest.fixture
def file_direct_send() -> bool:
    """同上，默认关掉。要验直发的用例自己覆盖它（见 file_test.py 那一组）。"""
    return False


@pytest.fixture
def broker_app(space: Workspace, pool: FakePool, tmp_path: Path) -> FastAPI:
    return create_broker_app(Broker(workspace=space, pool=pool, skills=SkillStore(tmp_path / "skill")))  # type: ignore[arg-type]


@pytest.fixture
def connection(broker_app: FastAPI) -> BrokerConnection:
    """到 broker 的连接，走 ASGI 传输 —— 真的 HTTP 语义，但不占端口。"""
    return BrokerConnection(
        base_url=BROKER_URL,
        client=httpx.AsyncClient(transport=httpx.ASGITransport(app=broker_app), base_url=BROKER_URL),
    )


@pytest.fixture
def queue(live_cache: Redis) -> TaskQueue:
    """测试用的队列。

    阻塞时间取得很短：worker 的主循环靠它回到「该停了没」的判断上，
    默认的 5 秒会让每条用例的收尾都等上一轮。
    """
    return TaskQueue(live_cache, consumer=TEST_CONSUMER, block_millisecond=TEST_BLOCK_MILLISECOND)


@pytest.fixture
def hasher() -> PasswordHasher:
    """调到最低档的哈希器。

    默认档一次要 64 MiB、几十毫秒，而这套用例每条都建号并登录一次 —— 那是上百次。
    档位是构造参数而不是全局设置，正是为了这种场合能换掉；生产走的仍是默认档。
    """
    return PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)


@pytest.fixture
def upload_max_byte() -> int:
    """上传上限默认给到生产的值。要验这道闸的用例自己覆盖它，那比造一个 64MB 的请求便宜。"""
    return DEFAULT_UPLOAD_MAX_BYTE


@pytest.fixture
def title_model() -> BaseChatModel:
    """起标题用的假模型。

    **不打真模型**：CI 里没有凭据，也不该花钱。给一个固定答案，让「提交之后标题
    自己出现了」这条路照样跑得通 —— 换成 None 顶掉的话，那一整段就等于没验。
    """
    return FakeListChatModel(responses=[FAKE_TITLE])


@pytest.fixture
def platform(
    connection: BrokerConnection,
    log: EventLog,
    live_engine: AsyncEngine,
    live_cache: Redis,
    queue: TaskQueue,
    hasher: PasswordHasher,
    file_direct_send: bool,
    upload_max_byte: int,
    title_model: BaseChatModel,
) -> Platform:
    repository = RunRepository(live_engine)
    thread = ThreadRepository(live_engine)
    return Platform(
        workspace=RemoteWorkspace(connection),
        log=log,
        submitter=RunSubmitter(repository=repository, queue=queue),
        queue=queue,
        repository=repository,
        connection=connection,
        backend_factory=RemoteBackendFactory(base_url=BROKER_URL),
        engine=live_engine,
        cache=live_cache,
        user=UserRepository(live_engine),
        group=GroupRepository(live_engine),
        join_request=JoinRequestRepository(live_engine),
        agent=AgentRepository(live_engine),
        skill=SkillRepository(live_engine),
        skill_store=RemoteSkillStore(connection),
        review=ReviewRepository(live_engine),
        thread=thread,
        title=TitleWriter(model=title_model, repository=thread),
        file_direct_send=file_direct_send,
        policy=QuotaPolicy(),
        cancel=CancelFlag(live_cache),
        usage=RunUsage(live_engine),
        rate=RateLimiter(live_cache, limit=TEST_RATE_LIMIT, window_second=TEST_RATE_WINDOW_SECOND),
        session=SessionStore(live_cache, ttl_second=DEFAULT_TTL_SECOND),
        upload_max_byte=upload_max_byte,
        password=hasher,
        session_ttl_second=DEFAULT_TTL_SECOND,
    )


@pytest.fixture
def worker(
    connection: BrokerConnection,
    space: Workspace,
    pool: FakePool,
    log: EventLog,
    agent: Agent,
    live_engine: AsyncEngine,
    live_cache: Redis,
    queue: TaskQueue,
) -> Worker:
    """跑在 api 同一个进程里的 worker。中间那条队列是真的。"""

    # backend 是同步的，没法走 ASGI 传输（那是纯异步的）。这里换成本地实现直接读写
    # 同一个 tmp 目录 —— agent 侧看到的接口一模一样，而 broker 那边读到的是同一批文件，
    # 因此「文件确实落在会话工作目录里」这条链路仍然是真的
    def backend_factory(thread_id: str) -> SandboxBackend:
        return SandboxBackend(workspace=space.path(thread_id), container=pool.current(thread_id) or FakeContainer())

    executor = RunExecutor(
        pool=RemoteSandboxPool(connection),
        log=log,
        agent=agent,
        repository=RunRepository(live_engine),
        cancel=CancelFlag(live_cache),
        skill_aligner=RemoteSkillStore(connection),
        backend_factory=backend_factory,
    )
    return Worker(queue=queue, executor=executor)


@pytest.fixture
def api(platform: Platform) -> FastAPI:
    return create_app(platform)


def signup(
    client: TestClient,
    platform: Platform,
    hasher: PasswordHasher,
    *,
    name: str,
    role: UserRole = UserRole.TEACHER,
) -> User:
    """建一个账号。

    **要在 `TestClient` 自己那条循环里建**：连接绑在创建它的循环上，在 pytest 那条
    循环里建号会把连接留进池子，应用侧再取到它就挂死在读上 —— 症状是超时，不指向循环。
    """
    assert client.portal is not None
    return client.portal.call(
        partial(platform.user.create, name=name, password_hash=hasher.hash(TEST_PASSWORD), role=role)
    )


def make_group(client: TestClient, platform: Platform, *, owner_id: str) -> Group:
    """建一个组，组主是给定的账号。

    与 `signup` 同一个理由要在客户端自己那条循环里建 —— 连接绑在创建它的循环上。
    """
    assert client.portal is not None
    return client.portal.call(partial(platform.group.create, name=f"课题组-{uuid4().hex[:8]}", owner_id=owner_id))


def login(client: TestClient, name: str) -> None:
    """登录，Cookie 由客户端自己收下。"""
    response = client.post("/api/auth/login", json={"name": name, "password": TEST_PASSWORD})
    assert response.status_code == httpx.codes.OK, response.text


@pytest.fixture
def admin(client: TestClient, platform: Platform, hasher: PasswordHasher) -> str:
    """一个管理员账号，**还没登录** —— `client` 那一侧登着的仍是教师。

    Returns:
        它的用户名，交给 `as_admin` 换身份。
    """
    account = signup(client, platform, hasher, name=f"admin-{uuid4().hex[:8]}", role=UserRole.ADMIN)
    return account.name


def as_admin(client: TestClient, admin: str) -> None:
    """把客户端换成管理员的身份。"""
    client.cookies.clear()
    login(client, admin)


@pytest.fixture
def client(
    api: FastAPI,
    worker: Worker,
    agent: Agent,
    live_cache: Redis,
    live_engine: AsyncEngine,
    platform: Platform,
    hasher: PasswordHasher,
) -> Iterator[TestClient]:
    """跑在 `TestClient` 自己那条事件循环上的客户端，外加一个同循环的 worker。

    **已经登录**：业务端点全部要求登录，不登的话每条用例都停在 401。要验未登录的行为
    就 `client.cookies.clear()`，那比再开一个客户端便宜。

    **收尾要回到那条循环里做**：asyncio 的连接绑在创建它的循环上，而这些连接是应用在
    portal 的循环里建的。等回到 pytest 的循环再关，那条循环已经没了 ——
    报出来是 `Event loop is closed`，而这个消息一点都不指向真正的原因。
    """
    with TestClient(api) as opened:
        assert opened.portal is not None
        opened.portal.start_task_soon(worker.run)
        try:
            # **建号与登录也要在 try 里**：它们一旦抛出，收尾就轮不到执行，
            # 而 worker 还挂在 portal 的循环里 —— 退出 TestClient 时会卡在 join 上，
            # 于是真正的异常一个字都看不到，只看到整套用例挂住
            owner = signup(opened, platform, hasher, name=f"teacher-{uuid4().hex[:8]}")
            login(opened, owner.name)
            yield opened
        finally:
            # **先放行再停 worker**：卡住的 agent 会让 `stop()` 一直等在
            # 「等在跑的 run 结束」上，整套用例就挂死在收尾里
            agent.blocked = False
            opened.portal.call(worker.stop)
            opened.portal.call(live_cache.connection_pool.disconnect)
            opened.portal.call(live_engine.dispose)


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
