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

from app.agent.circuit import McpCircuit
from app.agent.factory import Agent, create_model
from app.agent.trace import create_callback
from app.preset.mcp import McpRepository, McpTargetLoader
from app.preset.repository import AgentRepository
from app.preset.skill_remote import RemoteSkillStore
from app.run.archive import EventArchive
from app.run.cancel import CancelFlag
from app.run.executor import RunExecutor
from app.run.log import EventLog
from app.run.repository import RunRepository
from app.sandbox.remote import BrokerConnection, RemoteBackendFactory, RemoteSandboxPool
from app.store import postgres, redis
from app.store.checkpoint import CheckpointPool, open_checkpoint
from app.task.queue import TaskQueue
from app.worker.loop import Worker
from config import Settings

logger = logging.getLogger(__name__)


def consumer_name() -> str:
    """本进程在 consumer group 里的名字。

    带上 pid：本机手工起两个进程时只有 pid 不同，重名会让它们共用一份 pending 列表，
    「谁的任务」就分不清了。**容器里重启一次拿到的是同一个名字**（主机名与 pid 都没变），
    这不影响认领 —— `XAUTOCLAIM` 只看闲置多久，不看消息归谁。
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
        await self.backend_factory.aclose()
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

    mcp_catalog = McpRepository(engine)
    connection = BrokerConnection(base_url=settings.broker_url)
    backend_factory = RemoteBackendFactory(base_url=settings.broker_url)
    executor = RunExecutor(
        pool=RemoteSandboxPool(connection),
        log=EventLog(cache, archive=EventArchive(engine)),
        agent=Agent(
            model=create_model(settings),
            checkpointer=checkpoint.saver,
            # **只有这个进程驱动 agent**，因此追踪也只在这里挂。
            # 没配 Langfuse 时是 None，图上一个回调都不挂
            callback=create_callback(settings),
            subagent_loader=AgentRepository(engine),
            mcp_loader=McpTargetLoader(mcp_catalog, settings.mcp_credentials),
            # 计数在 Redis 而不是进程内：重启一次就清零的话，熔断阈值等于形同虚设
            mcp_recorder=McpCircuit(cache, mcp_catalog),
            recursion_limit=settings.agent_recursion_limit,
            context_trigger_token=settings.agent_context_trigger_token,
            tool_result_evict_token=settings.agent_tool_result_evict_token,
        ),
        repository=RunRepository(engine),
        cancel=CancelFlag(cache),
        skill_aligner=RemoteSkillStore(connection),
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
