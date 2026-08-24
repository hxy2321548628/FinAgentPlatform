"""Worker 入口同时驱动并停止主任务与记忆任务。"""

import asyncio
from dataclasses import dataclass
from typing import cast

from app.worker.main import _run_workers, _stop_workers
from app.worker.runtime import WorkerRuntime


class FakeMainWorker:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.stopped = asyncio.Event()
        self.stop_calls = 0

    async def run(self) -> None:
        self.started.set()
        await self.stopped.wait()

    async def stop(self) -> None:
        self.stop_calls += 1
        self.stopped.set()


class FakeMemoryLoop:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.stopped = asyncio.Event()
        self.stop_calls = 0

    async def run(self) -> None:
        self.started.set()
        await self.stopped.wait()

    def stop(self) -> None:
        self.stop_calls += 1
        self.stopped.set()


@dataclass
class FakeRuntime:
    worker: FakeMainWorker
    memory_loop: FakeMemoryLoop


async def test_main_runs_both_workers_and_one_stop_request_reaches_both() -> None:
    runtime = FakeRuntime(worker=FakeMainWorker(), memory_loop=FakeMemoryLoop())
    typed = cast(WorkerRuntime, runtime)
    running = asyncio.create_task(_run_workers(typed))
    await asyncio.wait_for(
        asyncio.gather(runtime.worker.started.wait(), runtime.memory_loop.started.wait()),
        timeout=0.1,
    )

    await _stop_workers(typed)
    await asyncio.wait_for(running, timeout=0.1)

    assert runtime.worker.stop_calls == 1
    assert runtime.memory_loop.stop_calls == 1
