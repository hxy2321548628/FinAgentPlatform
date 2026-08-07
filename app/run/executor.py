"""Run 执行器：领一次提问，申请沙箱，驱动智能体，把过程写成事件。

**提交与执行是分开的**：`submit` 立刻返回，执行在后台任务里跑 —— 一次分析要几分钟到
几十分钟，请求-响应承载不了。教师通过订阅事件日志看进度，不是等这个调用返回。

本期 run 只有四态（`queued → running → succeeded/failed`）：没有主动取消，没有 HITL
审批，也没有自动重试。失败时只在 `run.failed` 里给出 `retryable`，重不重试由人决定。
"""

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
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
    TokenUsage,
    now_ms,
)
from log import run_context
from run.log import EventLog
from sandbox.pool import QueuePositionCallback, SandboxQueueTimeoutError
from sandbox.remote import RemoteBackendFactory

logger = logging.getLogger(__name__)

# 一次分析的 chunk 流，由智能体装配层提供
type AgentRunner = Callable[[BackendProtocol, str, str], AsyncIterator[StreamChunk]]

# 按会话造 backend。注入进来而不是就地 new，是为了让测试能换掉传输层 ——
# 生产用发 HTTP 的远程实现，测试用直接读写临时目录的本地实现
type BackendFactory = Callable[[str], BackendProtocol]

UPDATES_MODE = "updates"


class WorkspaceProtocol(Protocol):
    """执行器对会话文件空间的全部要求。"""

    async def artifact_since(self, thread_id: str, since_ns: int) -> list[str]:
        """列出一次 run 产出的产物标识。"""
        ...


class SandboxPoolProtocol(Protocol):
    """执行器对沙箱池的全部要求。

    **申请不返回容器**：容器在 broker 那边，这个进程碰不到也不需要碰 ——
    它只要知道「沙箱备好了，可以开工了」。
    """

    async def acquire(self, thread_id: str, *, on_queued: QueuePositionCallback | None = None) -> None:
        """申请沙箱，必要时排队等待。"""
        ...

    async def release(self, thread_id: str) -> None:
        """归还沙箱。"""
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
        workspace: 各会话的文件空间，用来认领本次 run 的产物。
        log: 事件日志，执行过程中产生的一切都往这里写。
        runner: 驱动一次智能体执行并产出 chunk 流的函数。
        backend_factory: 按会话造 backend，不传则发 HTTP 给 broker。
    """

    def __init__(
        self,
        *,
        pool: SandboxPoolProtocol,
        workspace: WorkspaceProtocol,
        log: EventLog,
        runner: AgentRunner,
        backend_factory: BackendFactory | None = None,
    ) -> None:
        self._pool = pool
        self._workspace = workspace
        self._backend = backend_factory or RemoteBackendFactory()
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
        # 每个 run 跑在自己的任务里，任务启动时会复制一份 context，
        # 因此在这里绑定不会串到并发的其他 run 上
        with run_context(run_id=run.id, thread_id=run.thread_id):
            run.status = RunStatus.RUNNING
            self._emit(
                RunStartedEvent(ts=now_ms(), run_id=run.id, path=(), data=RunStartedData(thread_id=run.thread_id))
            )

            if not await self._acquire(run):
                return

            try:
                await self._consume(run)
            # 智能体那一侧什么都可能抛：模型断连、图跑飞、工具越界。宽捕获是刻意的 ——
            # 让异常逃出去只会让后台任务无声无息地死掉，订阅这个 run 的连接则永远等不到终态。
            except Exception as exc:
                logger.warning("run 执行失败", exc_info=True)
                self._fail(run, RunErrorCode.INTERNAL, str(exc), retryable=False)
            finally:
                await self._pool.release(run.thread_id)

    async def _acquire(self, run: Run) -> bool:
        """申请沙箱，把排队过程写成事件。失败时结束 run 并返回 False。"""

        def announce(position: int) -> None:
            self._emit(
                SandboxQueuedEvent(ts=now_ms(), run_id=run.id, path=(), data=SandboxQueuedData(position=position))
            )

        try:
            await self._pool.acquire(run.thread_id, on_queued=announce)
        # 同上：容器起不来、磁盘满、排队超时都得转成 run.failed，不能让任务静默消失
        except Exception as exc:
            logger.warning("run 申请沙箱失败", exc_info=True)
            queued_out = isinstance(exc, SandboxQueueTimeoutError)
            # 只有资源不足值得重试。其余按未分类错误处理 —— 盲目重试只是再炸一次，
            # 还多花一份 token
            code = RunErrorCode.SANDBOX_QUEUE_TIMEOUT if queued_out else RunErrorCode.INTERNAL
            self._fail(run, code, str(exc), retryable=queued_out)
            return False

        self._emit(SandboxReadyEvent(ts=now_ms(), run_id=run.id, path=(), data=SandboxReadyData()))
        return True

    async def _consume(self, run: Run) -> None:
        """消费智能体的流，逐个 chunk 映射成事件。"""
        backend = self._backend(run.thread_id)
        tokens = TokenUsage()
        # 产物按 mtime 判定，基准要在 agent 动手之前取，否则本次的产出会被漏掉
        started_at = time.time_ns()

        async for ns, mode, payload in self._runner(backend, run.thread_id, run.content):
            tokens = tokens + _token_usage(mode, payload)
            for event in map_chunk(ns, mode, payload, run_id=run.id):
                self._log.append(event)

        run.status = RunStatus.SUCCEEDED
        self._emit(
            RunFinishedEvent(
                ts=now_ms(),
                run_id=run.id,
                path=(),
                data=RunFinishedData(
                    tokens=tokens,
                    artifacts=await self._workspace.artifact_since(run.thread_id, started_at),
                ),
            )
        )

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


def _token_usage(mode: str, payload: object) -> TokenUsage:
    """从一个 chunk 里取出本次模型调用消耗的 token，按 cache 命中拆开。

    不复用映射层：那里的职责是产出前端要渲染的事件，而用量既不是事件也不该被前端逐条看到。
    """
    if mode != UPDATES_MODE or not isinstance(payload, dict):
        return TokenUsage()

    total = TokenUsage()
    for update in payload.values():
        if not isinstance(update, dict):
            continue
        message = update.get("messages")
        if not isinstance(message, list):
            continue
        for one in message:
            usage = getattr(one, "usage_metadata", None)
            if isinstance(usage, dict):
                total = total + _split_usage(usage)
    return total


def _split_usage(usage: dict[str, object]) -> TokenUsage:
    """把一条 `usage_metadata` 拆成三部分。

    `input_tokens` 是**含命中部分的总数**，相减才得到真正要付全价的那部分。
    换用不带 prompt cache 的模型时 `input_token_details` 整个不存在，按零命中处理。
    """
    detail = usage.get("input_token_details")
    cache_read = _as_int(detail.get("cache_read")) if isinstance(detail, dict) else 0
    input_total = _as_int(usage.get("input_tokens"))
    return TokenUsage(
        input_cache_read=cache_read,
        input_uncached=max(0, input_total - cache_read),
        output=_as_int(usage.get("output_tokens")),
    )


def _as_int(value: object) -> int:
    """取 `usage_metadata` 里的一个计数，缺失或形状不对时按 0 处理。

    计量出岔子不该让整个 run 失败 —— 教师拿到的分析结果是对的，只是这一次的账记不准。
    """
    return value if isinstance(value, int) else 0
