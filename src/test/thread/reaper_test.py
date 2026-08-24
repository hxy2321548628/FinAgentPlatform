"""软删 thread 的 workspace 补偿清理测试。"""

from datetime import UTC, datetime

from app.thread.purge import PurgeJob
from app.thread.reaper import sweep


class Repository:
    """只记录清理器落下的状态。"""

    def __init__(self) -> None:
        self.completed: list[str] = []
        self.failed: dict[str, str] = {}

    async def pending_purge(self, *, limit: int = 100) -> list[PurgeJob]:
        return [
            PurgeJob(thread_id="ok", requested_at=datetime.now(UTC), attempts=0, last_error=None),
            PurgeJob(thread_id="bad", requested_at=datetime.now(UTC), attempts=1, last_error="旧错误"),
        ][:limit]

    async def fail_purge(self, thread_id: str, error: str) -> None:
        self.failed[thread_id] = error

    async def complete_purge(self, thread_id: str) -> None:
        self.completed.append(thread_id)


class Workspace:
    """第二个 workspace 模拟 broker 失败。"""

    def __init__(self) -> None:
        self.seen: list[str] = []

    async def destroy(self, thread_id: str) -> None:
        self.seen.append(thread_id)
        if thread_id == "bad":
            raise RuntimeError("broker 不可达")


async def test_success_is_completed_and_failure_remains_retryable() -> None:
    repository = Repository()
    workspace = Workspace()

    assert await sweep(repository, workspace) == (1, 1)
    assert workspace.seen == ["ok", "bad"]
    assert repository.completed == ["ok"]
    assert repository.failed == {"bad": "broker 不可达"}
