"""网关运行时依赖的一组长生命周期对象，以及它们的装配。

这些对象**每个进程只有一份**，随应用启动建立、随关闭销毁。集中在这里而不是散落成
模块级单例，是为了让测试能整份换掉，也为了让「谁依赖谁」在一个地方看得清。

**这个进程不碰 Docker，也不碰宿主机上的 workspace 目录** —— 沙箱与文件都在
broker 那边，这里只有到它的一条 HTTP 连接。

**它也不再驱动智能体**：模型、checkpointer、沙箱申请全在 worker 那边。网关剩下的
只有三件事 —— 收提问并投进队列、查 run 的状态、把事件流转成 SSE。
"""

from dataclasses import dataclass

from fastapi import Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from artifact.repository import ArtifactRepository
from artifact.store import ArtifactStore
from auth.password import PasswordHasher
from auth.session import SessionStore
from config import Settings
from group.repository import GroupRepository, JoinRequestRepository
from quota.policy import QuotaPolicy
from quota.rate import RateLimiter
from quota.usage import RunUsage
from report.usage import UsageReport
from run.archive import EventArchive
from run.cancel import CancelFlag
from run.log import EventLog
from run.repository import RunRepository
from run.submitter import RunSubmitter
from sandbox.remote import BrokerConnection, RemoteBackendFactory, RemoteWorkspace
from store import postgres, redis
from task.queue import TaskQueue
from thread.repository import ThreadRepository
from user.repository import UserRepository

# 网关只投递不消费，consumer 名字用不上。给一个显式的常量而不是空串，
# 是为了万一有人拿它去 XREADGROUP 时能一眼看出是谁干的
PRODUCER_NAME = "api"


@dataclass(frozen=True)
class Platform:
    """网关持有的运行时。"""

    workspace: RemoteWorkspace
    log: EventLog
    submitter: RunSubmitter
    # 投递用的是 `submitter`，这里单独摆出来只为一件事：抓取指标时要看队列积压。
    # 与 submitter 持有的是同一个实例 —— 各建一个的话，两处各自 `ensure_group`，
    # 而积压读数来自哪一个就成了运气
    queue: TaskQueue
    repository: RunRepository
    connection: BrokerConnection
    backend_factory: RemoteBackendFactory
    engine: AsyncEngine
    cache: Redis
    user: UserRepository
    group: GroupRepository
    join_request: JoinRequestRepository
    thread: ThreadRepository
    artifacts: ArtifactRepository
    # 产物的对象存储。**只用来签 URL 与（没有 nginx 时）取字节**，从不写入 ——
    # 写在 broker 那一侧，那是唯一碰得到 workspace 的进程
    artifact: ArtifactStore | None
    # 走不走 nginx 直发。开着时这个进程一个字节都不经手；关掉时自己从对象存储取回来
    # 再转发，那是开发机直接跑 uvicorn 的路 —— X-Accel-Redirect 只在 nginx 后面有效
    artifact_direct_send: bool
    session: SessionStore
    policy: QuotaPolicy
    cancel: CancelFlag
    usage: RunUsage
    # 成本看板的数据源。**与 `usage` 是两件事**：那个是闸门（永远带 user 过滤），
    # 这个是账本（跨用户聚合）
    usage_report: UsageReport
    rate: RateLimiter
    password: PasswordHasher
    # Cookie 的 max-age 要与 session 在 Redis 里的 TTL 一致。两边分别配的话，
    # 短的那一侧到期时另一侧还留着 —— 症状是「明明还没登出却要重新登录」，或者反过来
    session_ttl_second: int


async def build_platform(settings: Settings) -> Platform:
    """按配置装配一整套运行时，并当场确认两个外部存储都连得上。

    **体检失败即启动失败**：这与缺 `DEEPSEEK_API_KEY` 时构造 `Settings` 就抛是同一个规矩。

    Args:
        settings: 平台配置。

    Returns:
        可直接交给应用使用的运行时。

    Raises:
        PostgresUnavailableError: 连不上 Postgres。
        RedisUnavailableError: 连不上 Redis。
    """
    engine = postgres.create_engine(settings.postgres_dsn())
    await postgres.check(engine)
    cache = redis.create_client(settings.redis_url)
    await redis.check(cache)

    connection = BrokerConnection(base_url=settings.broker_url)
    repository = RunRepository(engine)
    queue = TaskQueue(cache, consumer=PRODUCER_NAME)
    policy = QuotaPolicy(
        token_daily=settings.quota_token_daily,
        concurrent_run=settings.quota_concurrent_run,
        output_weight=settings.quota_output_weight,
    )
    return Platform(
        workspace=RemoteWorkspace(connection),
        # 网关只读事件，不写。给它归档是为了让「Stream 里已经没有的那段历史」也读得到
        log=EventLog(cache, archive=EventArchive(engine)),
        submitter=RunSubmitter(repository=repository, queue=queue),
        queue=queue,
        repository=repository,
        connection=connection,
        backend_factory=RemoteBackendFactory(base_url=settings.broker_url),
        engine=engine,
        cache=cache,
        user=UserRepository(engine),
        group=GroupRepository(engine),
        join_request=JoinRequestRepository(engine),
        thread=ThreadRepository(engine),
        artifacts=ArtifactRepository(engine),
        artifact=ArtifactStore(client=settings.minio_client(), bucket=settings.minio_bucket),
        artifact_direct_send=settings.artifact_direct_send,
        policy=policy,
        cancel=CancelFlag(cache),
        usage=RunUsage(engine, output_weight=policy.output_weight),
        usage_report=UsageReport(engine),
        rate=RateLimiter(cache, limit=settings.rate_limit, window_second=settings.rate_limit_window_second),
        session=SessionStore(cache, ttl_second=settings.session_ttl_second),
        password=PasswordHasher(),
        session_ttl_second=settings.session_ttl_second,
    )


def get_platform(request: Request) -> Platform:
    """路由取运行时的依赖项。"""
    platform: Platform = request.app.state.platform
    return platform
