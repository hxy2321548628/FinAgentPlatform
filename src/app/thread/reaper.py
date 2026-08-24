"""软删 thread 的 workspace 补偿清理。

API 首次销毁失败时，``thread_purge_jobs`` 会保留待办；本命令可由 cron 反复运行：

    cd src && uv run python -m app.thread.reaper
"""

import asyncio
import logging
from typing import Protocol

from app.sandbox.remote import BrokerConnection, RemoteWorkspace
from app.store import postgres
from app.thread.purge import PurgeJob
from app.thread.repository import ThreadRepository
from config import Settings
from log import configure

logger = logging.getLogger(__name__)


class PurgeRepositoryProtocol(Protocol):
    """清理器对持久待办的最小依赖。"""

    async def pending_purge(self, *, limit: int = 100) -> list[PurgeJob]:
        """列出尚未成功的清理任务。"""
        ...

    async def fail_purge(self, thread_id: str, error: str) -> None:
        """记录失败并保留待办。"""
        ...

    async def complete_purge(self, thread_id: str) -> None:
        """标记已清理。"""
        ...


class WorkspaceDestroyerProtocol(Protocol):
    """清理器只需要 broker 的销毁原语。"""

    async def destroy(self, thread_id: str) -> None:
        """销毁沙箱与整个 workspace。"""
        ...


async def sweep(
    repository: PurgeRepositoryProtocol,
    workspace: WorkspaceDestroyerProtocol,
    *,
    limit: int = 100,
) -> tuple[int, int]:
    """跑一批清理，返回成功数与失败数。"""
    completed = 0
    failed = 0
    for job in await repository.pending_purge(limit=limit):
        try:
            await workspace.destroy(job.thread_id)
        except Exception as exc:
            failed += 1
            await repository.fail_purge(job.thread_id, str(exc)[:2_000])
            logger.error("workspace 补偿清理失败：thread_id=%s", job.thread_id, exc_info=True)
            continue
        await repository.complete_purge(job.thread_id)
        completed += 1
        logger.info("workspace 补偿清理完成：thread_id=%s", job.thread_id)
    return completed, failed


async def _main() -> None:
    settings = Settings()
    engine = postgres.create_engine(settings.postgres_dsn())
    await postgres.check(engine)
    connection = BrokerConnection(base_url=settings.broker_url)
    try:
        completed, failed = await sweep(ThreadRepository(engine), RemoteWorkspace(connection))
        logger.info("workspace 补偿清理结束：成功 %d，失败 %d", completed, failed)
        if failed:
            raise RuntimeError(f"仍有 {failed} 个 workspace 清理失败")
    finally:
        await connection.aclose()
        await engine.dispose()


def main() -> None:
    """命令行入口；仍有失败时以非零状态退出。"""
    configure()
    asyncio.run(_main())


if __name__ == "__main__":
    main()
