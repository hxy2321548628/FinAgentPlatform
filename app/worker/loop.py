"""Worker 的主循环：领任务、跑、ack。

**并发在进程内**：一次分析里绝大部分时间在等模型和等沙箱，一个 worker 同时驱动
若干个 run 才用得满。副本数解决的是「这台进程挂了怎么办」，不是吞吐。

**ack 在 `finally` 里**，因此正常结束与业务失败都会 ack —— 失败的 run 已经写了
`run.failed` 事件，重投它只会再失败一次，还多花一份 token。只有进程被 `kill -9`
这种「没机会走到 finally」的情况才留下 pending，那正是要重投的那一类。
"""

import asyncio
import contextlib
import logging
from typing import Protocol

from task.queue import Delivery, RunTask, TaskQueue

logger = logging.getLogger(__name__)

# 一个 worker 同时驱动几个 run
DEFAULT_CONCURRENCY = 8

# 多久宣告一次「我还活着」。要**明显小于**队列的认领阈值，
# 否则健康的 worker 会被别人当成已经死了
DEFAULT_HEARTBEAT_SECOND = 15.0


class RunExecutorProtocol(Protocol):
    """worker 对执行器的全部要求：跑完一条任务，且不抛。"""

    async def execute(self, task: RunTask) -> None:
        """跑完一条任务。"""
        ...


class Worker:
    """领任务、跑、ack 的主循环。

    Args:
        queue: 任务队列。
        executor: 真正驱动一次分析的执行器。
        concurrency: 同时驱动几个 run。
        heartbeat_second: 多久给持有的消息续一次命。
    """

    def __init__(
        self,
        *,
        queue: TaskQueue,
        executor: RunExecutorProtocol,
        concurrency: int = DEFAULT_CONCURRENCY,
        heartbeat_second: float = DEFAULT_HEARTBEAT_SECOND,
    ) -> None:
        self._queue = queue
        self._executor = executor
        self._concurrency = concurrency
        self._heartbeat = heartbeat_second
        self._running: set[asyncio.Task[None]] = set()
        self._stopping = asyncio.Event()
        self._started = asyncio.Event()
        self._finished = asyncio.Event()

    async def run(self) -> None:
        """一直领任务，直到有人叫停。"""
        self._started.set()
        await self._queue.ensure_group()
        logger.info("worker 开始领任务")
        try:
            while not self._stopping.is_set():
                if len(self._running) >= self._concurrency:
                    await asyncio.wait(self._running, return_when=asyncio.FIRST_COMPLETED)
                    continue
                delivery = await self._queue.reserve()
                if delivery is None:
                    continue
                self._spawn(delivery)
            await self._drain()
        finally:
            self._finished.set()

    async def stop(self) -> None:
        """叫停主循环，并等它真的退出来。

        **不打断在跑的 run**：它们已经烧了 token，掐掉等于白花。
        滚动重启时这段等待就是「优雅停机」的全部内容。

        **要等主循环退出，不只是等在跑的 run**：领任务那一步可能正阻塞着，
        它醒来之后还会再下几条 Redis 命令。不等的话，调用方紧接着关连接池就会打架。

        先等主循环起来再等它结束：停机信号可能赶在 `run` 被调度之前就到了，
        那时直接等「结束」会立刻返回，而主循环随后才开始下命令。
        """
        self._stopping.set()
        await self._started.wait()
        await self._finished.wait()

    def _spawn(self, delivery: Delivery) -> None:
        task = asyncio.create_task(self._handle(delivery))
        self._running.add(task)
        task.add_done_callback(self._running.discard)

    async def _handle(self, delivery: Delivery) -> None:
        """跑完一条任务，无论结果如何都 ack。"""
        beat = asyncio.create_task(self._keep_alive(delivery.id))
        try:
            await self._executor.execute(delivery.task)
        finally:
            beat.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await beat
            await self._queue.ack(delivery.id)

    async def _keep_alive(self, message_id: str) -> None:
        """定期给持有的消息续命，直到被取消。"""
        while True:
            await asyncio.sleep(self._heartbeat)
            await self._queue.touch(message_id)

    async def _drain(self) -> None:
        if self._running:
            await asyncio.gather(*self._running, return_exceptions=True)
