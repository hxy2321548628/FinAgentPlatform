"""Worker 持有的一组长生命周期对象，以及它们的装配。

**这个进程不碰 Docker，也不碰宿主机上的 workspace 目录** —— 与 api 一样，
沙箱与文件都在 broker 那边（ADR-0004 的边界没有因为拆出 worker 而变）。
它比 api 多的是：模型、checkpointer、以及一条到任务队列的消费连接。
"""

import logging
import os
import socket
from dataclasses import dataclass

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from agent.factory import create_model, create_runner
from config import Settings
from run.archive import EventArchive
from run.executor import RunExecutor
from run.log import EventLog
from run.repository import RunRepository
from sandbox.remote import BrokerConnection, RemoteBackendFactory, RemoteSandboxPool, RemoteWorkspace
from store import postgres, redis
from store.checkpoint import CheckpointPool, open_checkpoint
from task.queue import TaskQueue
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

    async def aclose(self) -> None:
        """归还所有外部连接。"""
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
    executor = RunExecutor(
        pool=RemoteSandboxPool(connection),
        workspace=RemoteWorkspace(connection),
        log=EventLog(cache, archive=EventArchive(engine)),
        runner=create_runner(model=create_model(settings), checkpointer=checkpoint.saver),
        repository=RunRepository(engine),
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
    )
