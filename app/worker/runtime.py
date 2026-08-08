"""Worker 持有的一组长生命周期对象，以及它们的装配。

**这个进程不碰 Docker，也不碰宿主机上的 workspace 目录** —— 与 api 一样，
沙箱与文件都在 broker 那边（ADR-0004 的边界没有因为拆出 worker 而变）。
它比 api 多的是：模型、checkpointer、以及一条到任务队列的消费连接。
"""

import logging
import os
import socket
from dataclasses import dataclass
from wsgiref.simple_server import WSGIServer

from prometheus_client import CollectorRegistry, start_http_server
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from agent.factory import Agent, create_model
from artifact.repository import ArtifactRepository
from config import Settings
from metric.llm import LlmMetric
from run.archive import EventArchive
from run.cancel import CancelFlag
from run.executor import RunExecutor
from run.log import EventLog
from run.repository import RunRepository
from sandbox.remote import BrokerConnection, RemoteBackendFactory, RemoteSandboxPool, RemoteWorkspace
from store import postgres, redis
from store.checkpoint import CheckpointPool, open_checkpoint
from task.queue import TaskQueue
from telemetry.llm import callback as trace_callback
from worker.loop import Worker

logger = logging.getLogger(__name__)


def consumer_name() -> str:
    """本进程在 consumer group 里的名字。

    带上 pid：compose 里两个副本的主机名不同，而本机手工起两个进程时只有 pid 不同。
    重名会让两个进程共用一份 pending 列表，「谁的任务」就分不清了。
    """
    return f"{socket.gethostname()}-{os.getpid()}"


@dataclass(frozen=True)
class WorkerRuntime:
    """worker 持有的运行时。"""

    worker: Worker
    queue: TaskQueue
    engine: AsyncEngine
    cache: Redis
    connection: BrokerConnection
    backend_factory: RemoteBackendFactory
    checkpoint_pool: CheckpointPool
    # 抓取端口的服务器。**可以没有** —— 端口被占时 worker 照常跑分析，
    # 只是在 Prometheus 上显示为 down，见 `_serve_metric`
    metric_server: WSGIServer | None = None

    async def aclose(self) -> None:
        """归还所有外部连接。"""
        if self.metric_server is not None:
            self.metric_server.shutdown()
        self.backend_factory.close()
        await self.connection.aclose()
        await self.engine.dispose()
        await self.cache.aclose()
        await self.checkpoint_pool.close()


async def build_worker(settings: Settings) -> WorkerRuntime:
    """按配置装配一整套 worker 运行时。

    连不上外部存储时在这里就抛，与 api 同一个规矩。

    Args:
        settings: 平台配置。

    Returns:
        可直接跑起来的 worker 运行时。

    Raises:
        PostgresUnavailableError: 连不上 Postgres。
        RedisUnavailableError: 连不上 Redis。
    """
    engine = postgres.create_engine(settings.postgres_dsn())
    await postgres.check(engine)
    cache = redis.create_client(settings.redis_url)
    await redis.check(cache)
    checkpoint = await open_checkpoint(settings.postgres_conninfo())

    connection = BrokerConnection(base_url=settings.broker_url)
    backend_factory = RemoteBackendFactory(base_url=settings.broker_url)
    # **只有这个进程调模型**，因此「一次调用有多慢、失不失败」也只有它量得到。
    # 指标与追踪各挂一个回调，不合成一个：前者攒的是所有调用的耗时分布，
    # 后者给的是「这一次 run 里第 3 轮调用花了多久」，两者的失效方式完全不同
    llm = LlmMetric()
    executor = RunExecutor(
        pool=RemoteSandboxPool(connection),
        workspace=RemoteWorkspace(connection),
        log=EventLog(cache, archive=EventArchive(engine)),
        agent=Agent(
            model=create_model(settings, callback=[llm.callback(), trace_callback()]),
            checkpointer=checkpoint.saver,
        ),
        repository=RunRepository(engine),
        cancel=CancelFlag(cache),
        artifacts=ArtifactRepository(engine),
        backend_factory=backend_factory,
    )
    queue = TaskQueue(
        cache,
        consumer=consumer_name(),
        claim_idle_millisecond=settings.worker_claim_idle_millisecond,
    )
    return WorkerRuntime(
        worker=Worker(
            queue=queue,
            executor=executor,
            concurrency=settings.worker_concurrency,
            heartbeat_second=settings.worker_heartbeat_second,
        ),
        queue=queue,
        engine=engine,
        cache=cache,
        connection=connection,
        backend_factory=backend_factory,
        checkpoint_pool=checkpoint.pool,
        metric_server=_serve_metric(settings.worker_metric_port, llm.registry),
    )


def _serve_metric(port: int, registry: CollectorRegistry) -> WSGIServer | None:
    """把指标挂到一个端口上给 Prometheus 抓。

    **worker 不是 HTTP 服务**，这是它唯一监听的端口，只服务抓取。

    **端口起不来不拦启动**：worker 的职责是把分析跑完，为一个观测端口拒绝启动，
    等于把观测手段变成可用性风险。这不是静默降级 —— 抓不到的那一刻 Prometheus 的
    `up` 就是 0，告警规则看得见（本机手工起第二个 worker 时正是这条路：
    两个进程抢同一个端口，后起的那个只是不上报）。
    """
    if port <= 0:
        logger.info("未配 worker 指标端口，本进程不暴露指标")
        return None
    try:
        server, _ = start_http_server(port, registry=registry)
    except OSError:
        logger.error("worker 指标端口起不来，本进程在 Prometheus 上会显示为 down：port=%s", port, exc_info=True)
        return None
    return server
