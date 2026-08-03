"""Run 执行器：领一次提问，申请沙箱，驱动智能体，把过程写成事件。

**提交与执行是分开的**：`submit` 立刻返回，执行在后台任务里跑 —— 一次分析要几分钟到
几十分钟，请求-响应承载不了。教师通过订阅事件日志看进度，不是等这个调用返回。

本期 run 只有四态（`queued → running → succeeded/failed`）：没有主动取消，没有 HITL
审批，也没有自动重试。失败时只在 `run.failed` 里给出 `retryable`，重不重试由人决定。
"""

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from deepagents.backends.protocol import BackendProtocol

from event.mapper import StreamChunk, map_chunk
from event.model import (
    Event,
    RunErrorCode,
    RunFailedData,
    RunFailedEvent,
    RunFinishedData,
    RunFinishedEvent,
    RunStartedData,
    RunStartedEvent,
    RunStatus,
    SandboxQueuedData,
    SandboxQueuedEvent,
    SandboxReadyData,
    SandboxReadyEvent,
    now_ms,
)
from run.log import EventLog
from sandbox.backend import SandboxBackend
from sandbox.container import ContainerProtocol
from sandbox.pool import QueuePositionCallback, SandboxQueueTimeoutError

logger = logging.getLogger(__name__)

# 一次分析的 chunk 流，由智能体装配层提供
type AgentRunner = Callable[[BackendProtocol, str, str], AsyncIterator[StreamChunk]]

UPDATES_MODE = "updates"


class SandboxPoolProtocol(Protocol):
    """执行器对沙箱池的全部要求。"""

    def workspace_for(self, thread_id: str) -> Path:
        """返回一个 thread 的 workspace 目录，不存在则创建。"""
        ...

    async def acquire(self, thread_id: str, *, on_queued: QueuePositionCallback | None = None) -> ContainerProtocol:
        """取得容器，必要时排队等待。"""
        ...

    async def release(self, thread_id: str) -> None:
        """归还容器。"""
        ...


@dataclass
class Run:
    """一次提问的执行记录。"""

    id: str
    thread_id: str
    content: str
    status: RunStatus


class RunExecutor:
    """把提问变成一串事件。

    Args:
        pool: 沙箱池。
        log: 事件日志，执行过程中产生的一切都往这里写。
        runner: 驱动一次智能体执行并产出 chunk 流的函数。
    """

    def __init__(self, *, pool: SandboxPoolProtocol, log: EventLog, runner: AgentRunner) -> None:
        self._pool = pool
        self._log = log
        self._runner = runner
        self._run: dict[str, Run] = {}
        self._task: dict[str, asyncio.Task[None]] = {}

    async def submit(self, *, thread_id: str, content: str) -> Run:
        """接下一次提问并立刻返回，执行在后台进行。

        Args:
            thread_id: 提问所属的会话。
            content: 教师的问题。

        Returns:
            状态为 `queued` 的 run 记录，`id` 用于订阅事件与查询状态。
        """
        run = Run(id=uuid4().hex, thread_id=thread_id, content=content, status=RunStatus.QUEUED)
        self._run[run.id] = run
        self._task[run.id] = asyncio.create_task(self._drive(run))
        return run

    def get(self, run_id: str) -> Run | None:
        """按 id 查一次 run，不存在时返回 None。"""
        return self._run.get(run_id)

    async def wait(self, run_id: str) -> None:
        """等一个 run 跑完。未知的 run 直接返回。"""
        task = self._task.get(run_id)
        if task is not None:
            await task

    async def aclose(self) -> None:
        """等所有在跑的 run 结束。"""
        await asyncio.gather(*self._task.values(), return_exceptions=True)

    async def _drive(self, run: Run) -> None:
        run.status = RunStatus.RUNNING
        self._emit(RunStartedEvent(ts=now_ms(), run_id=run.id, path=(), data=RunStartedData(thread_id=run.thread_id)))

        container = await self._acquire(run)
        if container is None:
            return

        try:
            await self._consume(run, container)
        # 智能体那一侧什么都可能抛：模型断连、图跑飞、工具越界。宽捕获是刻意的 ——
        # 让异常逃出去只会让后台任务无声无息地死掉，订阅这个 run 的连接则永远等不到终态。
        except Exception as exc:
            logger.warning("run 执行失败：run_id=%s", run.id, exc_info=True)
            self._fail(run, RunErrorCode.INTERNAL, str(exc), retryable=False)
        finally:
            await self._pool.release(run.thread_id)

    async def _acquire(self, run: Run) -> ContainerProtocol | None:
        """申请沙箱，把排队过程写成事件。失败时结束 run 并返回 None。"""

        def announce(position: int) -> None:
            self._emit(
                SandboxQueuedEvent(ts=now_ms(), run_id=run.id, path=(), data=SandboxQueuedData(position=position))
            )

        try:
            container = await self._pool.acquire(run.thread_id, on_queued=announce)
        # 同上：容器起不来、磁盘满、排队超时都得转成 run.failed，不能让任务静默消失
        except Exception as exc:
            logger.warning("run 申请沙箱失败：run_id=%s", run.id, exc_info=True)
            queued_out = isinstance(exc, SandboxQueueTimeoutError)
            # 只有资源不足值得重试。其余按未分类错误处理 —— 盲目重试只是再炸一次，
            # 还多花一份 token
            code = RunErrorCode.SANDBOX_QUEUE_TIMEOUT if queued_out else RunErrorCode.INTERNAL
            self._fail(run, code, str(exc), retryable=queued_out)
            return None

        self._emit(SandboxReadyEvent(ts=now_ms(), run_id=run.id, path=(), data=SandboxReadyData()))
        return container

    async def _consume(self, run: Run, container: ContainerProtocol) -> None:
        """消费智能体的流，逐个 chunk 映射成事件。"""
        backend = SandboxBackend(workspace=self._pool.workspace_for(run.thread_id), container=container)
        tokens_used = 0

        async for ns, mode, payload in self._runner(backend, run.thread_id, run.content):
            tokens_used += _token_usage(mode, payload)
            for event in map_chunk(ns, mode, payload, run_id=run.id):
                self._log.append(event)

        run.status = RunStatus.SUCCEEDED
        self._emit(RunFinishedEvent(ts=now_ms(), run_id=run.id, path=(), data=RunFinishedData(tokens_used=tokens_used)))

    def _fail(self, run: Run, code: RunErrorCode, message: str, *, retryable: bool) -> None:
        run.status = RunStatus.FAILED
        self._emit(
            RunFailedEvent(
                ts=now_ms(),
                run_id=run.id,
                path=(),
                data=RunFailedData(code=code, message=message or code.value, retryable=retryable),
            )
        )

    def _emit(self, event: Event) -> None:
        self._log.append(event)


def _token_usage(mode: str, payload: object) -> int:
    """从一个 chunk 里取出本次模型调用消耗的 token。

    不复用映射层：那里的职责是产出前端要渲染的事件，而用量既不是事件也不该被前端逐条看到。
    取 `input + output` 而不是 `total_tokens`，是因为实测二者对不上 ——
    命中 prompt cache 的部分在 total 里另算，按 cache 拆分的口径要等配额落地时再定。
    """
    if mode != UPDATES_MODE or not isinstance(payload, dict):
        return 0

    total = 0
    for update in payload.values():
        if not isinstance(update, dict):
            continue
        message = update.get("messages")
        if not isinstance(message, list):
            continue
        for one in message:
            usage = getattr(one, "usage_metadata", None)
            if isinstance(usage, dict):
                total += int(usage.get("input_tokens", 0)) + int(usage.get("output_tokens", 0))
    return total
