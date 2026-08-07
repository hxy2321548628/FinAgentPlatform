"""Run 执行器：接一条任务，申请沙箱，驱动智能体，把过程写成事件。

**这里只跑 worker 进程里的那一半。** 提交那一半在 `run/submitter.py` —— 一次分析要
几分钟到几十分钟，请求-响应承载不了，两侧的交界是队列里的一条任务消息。教师通过订阅
事件日志看进度。

**一次 run 可能被执行多次**：每轮审批之后都作为一条新任务重新投递，从 checkpoint
接着走。因此「执行一次」与「跑完一个 run」不是一回事 —— 停在等人确认上也是正常返回，
调用方照常 ack，挂起期间既不持有队列消息也不持有沙箱。

没有自动重试：失败时只在 `run.failed` 里给出 `retryable`，重不重试由人决定。
"""

import logging
import time
from collections.abc import AsyncIterator, Callable
from typing import Protocol

from deepagents.backends.protocol import BackendProtocol

from event.mapper import StreamChunk, map_chunk
from event.model import (
    Event,
    InterruptAction,
    InterruptData,
    InterruptEvent,
    RunCancelledData,
    RunCancelledEvent,
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
from run.decision import to_resume
from run.log import EventLog
from run.repository import Run
from sandbox.pool import SandboxQueueTimeoutError
from sandbox.remote import AsyncQueuePositionCallback, RemoteBackendFactory
from task.queue import RunTask

logger = logging.getLogger(__name__)


class AgentProtocol(Protocol):
    """执行器对智能体的全部要求：开跑、恢复、问有没有在等人确认。

    编排框架的概念（graph、Command、checkpoint_ns）一个都不在这里 ——
    换掉框架时改的是装配层，不是执行器。
    """

    def stream(self, backend: BackendProtocol, thread_id: str, content: str) -> AsyncIterator[StreamChunk]:
        """第一次跑一个提问。"""
        ...

    def resume(
        self, backend: BackendProtocol, thread_id: str, decisions: list[dict[str, object]]
    ) -> AsyncIterator[StreamChunk]:
        """带着教师的决策从中断点接着跑。"""
        ...

    async def pending(self, backend: BackendProtocol, thread_id: str) -> list[InterruptAction]:
        """有没有在等人确认。"""
        ...


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

    async def acquire(
        self, thread_id: str, *, holder: str, on_queued: AsyncQueuePositionCallback | None = None
    ) -> None:
        """申请沙箱，必要时排队等待。"""
        ...

    async def release(self, thread_id: str, *, holder: str) -> None:
        """按持有者归还沙箱。"""
        ...


class RunRepositoryProtocol(Protocol):
    """执行器对 run 元数据仓储的全部要求：只有几次状态流转。

    建行在提交那一侧，查状态在端点那一侧，都不经过执行器。
    """

    async def start(self, run_id: str) -> bool:
        """标记开跑，并回答这一次是不是自己改的。"""
        ...

    async def succeed(self, run_id: str, *, tokens: TokenUsage) -> bool:
        """标记跑完，并回答这一次是不是自己写下的终态。"""
        ...

    async def fail(self, run_id: str, *, code: RunErrorCode, message: str) -> bool:
        """标记失败，并回答这一次是不是自己写下的终态。"""
        ...

    async def cancel(self, run_id: str, *, tokens: TokenUsage | None = None) -> bool:
        """标记取消，并回答这一次是不是自己改的。"""
        ...

    async def wait_approval(self, run_id: str, *, tokens: TokenUsage) -> bool:
        """标记等人确认，并回答这一次是不是自己改的。"""
        ...


class CancelFlagProtocol(Protocol):
    """执行器对取消标志的全部要求：只有读。

    立标志是 api 那一侧的事 —— worker 只负责发现它。
    """

    async def is_raised(self, run_id: str) -> bool:
        """有没有人要停这个 run。"""
        ...


class RunCancelledError(Exception):
    """教师取消了这个 run。

    **不是失败**，因此不走 `run.failed` 那条路：前端不该显示重试按钮，也不该报错。
    用异常而不是返回值，是因为要停的位置在 `astream` 的循环里，
    而收尾（归还沙箱）在几层之外的 `finally` 上。
    """


class RunExecutor:
    """把一条任务变成一串事件。

    Args:
        pool: 沙箱池。
        workspace: 各会话的文件空间，用来认领本次 run 的产物。
        log: 事件日志，执行过程中产生的一切都往这里写。
        agent: 智能体，负责开跑、续跑与「有没有在等人确认」。
        repository: run 元数据的仓储，状态流转往这里落。
        backend_factory: 按会话造 backend，不传则发 HTTP 给 broker。
    """

    def __init__(
        self,
        *,
        pool: SandboxPoolProtocol,
        workspace: WorkspaceProtocol,
        log: EventLog,
        agent: AgentProtocol,
        repository: RunRepositoryProtocol,
        cancel: CancelFlagProtocol,
        backend_factory: BackendFactory | None = None,
    ) -> None:
        self._pool = pool
        self._workspace = workspace
        self._backend = backend_factory or RemoteBackendFactory()
        self._log = log
        self._agent = agent
        self._repository = repository
        self._cancel = cancel

    async def execute(self, task: RunTask) -> None:
        """跑完一条已经领到手的任务，或者把它停在「等人确认」上。

        **不抛异常**：智能体那一侧什么都可能出事，但那些都该变成 `run.failed` 事件，
        而不是让调用方（worker 的主循环）去接。

        **停在等人确认时也是正常返回** —— 调用方照常 ack。ack 表示「这一段执行结束了」，
        不表示「整个 run 结束了」：挂起期间不持有队列消息，也不持有沙箱，
        那正是「不占用任何 worker 资源，可挂起数小时」的字面实现。

        Args:
            task: 从队列里领到的任务。
        """
        run = Run(id=task.run_id, thread_id=task.thread_id, status=RunStatus.RUNNING)
        await self._drive(run, task, task.user_id)

    async def _drive(self, run: Run, task: RunTask, user_id: str | None) -> None:
        # 每个 run 跑在自己的任务里，任务启动时会复制一份 context，
        # 因此在这里绑定不会串到并发的其他 run 上
        with run_context(run_id=run.id, thread_id=run.thread_id, user_id=user_id):
            # **开跑之前先看一眼**：取消一个还在排队的 run 时，任务消息仍然躺在队列里，
            # worker 迟早会领到它。不在这里挡一道，那次取消就只是把状态改了一下，
            # 而分析照跑不误 —— 那正是「取消没停下来」最典型的形态
            if await self._cancel.is_raised(run.id):
                logger.info("run 在开跑前已被取消，直接收手")
                await self._stop(run, TokenUsage())
                return

            # 状态改不动就说明这个 run 已经走到终态了 —— 消息重投时会撞上这一条。
            # 硬跑下去等于让一次已经结束的分析又跑一遍，还多花一份 token
            if not await self._repository.start(run.id):
                logger.info("run 已经有终态了，这一次投递不再执行")
                return

            resumed = task.decisions is not None
            await self._emit(
                RunStartedEvent(
                    ts=now_ms(),
                    run_id=run.id,
                    path=(),
                    data=RunStartedData(thread_id=run.thread_id, resumed=resumed),
                )
            )

            if not await self._acquire(run):
                return

            try:
                await self._consume(run, task)
            except RunCancelledError:
                # 取消不是失败。沙箱在 finally 里归还，已经写入的 checkpoint 原样留着 ——
                # 那是「从该点还能续跑」的全部依据
                logger.info("run 已按教师的要求停下")
            # 智能体那一侧什么都可能抛：模型断连、图跑飞、工具越界。宽捕获是刻意的 ——
            # 让异常逃出去只会让后台任务无声无息地死掉，订阅这个 run 的连接则永远等不到终态。
            except Exception as exc:
                logger.warning("run 执行失败", exc_info=True)
                await self._fail(run, RunErrorCode.INTERNAL, str(exc), retryable=False)
            finally:
                await self._pool.release(run.thread_id, holder=run.id)

    async def _acquire(self, run: Run) -> bool:
        """申请沙箱，把排队过程写成事件。失败时结束 run 并返回 False。"""

        async def announce(position: int) -> None:
            await self._emit(
                SandboxQueuedEvent(ts=now_ms(), run_id=run.id, path=(), data=SandboxQueuedData(position=position))
            )

        try:
            # **持有者取 run 标识**：崩溃恢复接着跑的是同一个 run，它再申请一次
            # 同一个容器时不该被算成第二个租约 —— 那一个永远不会有人来还
            await self._pool.acquire(run.thread_id, holder=run.id, on_queued=announce)
        # 同上：容器起不来、磁盘满、排队超时都得转成 run.failed，不能让任务静默消失
        except Exception as exc:
            logger.warning("run 申请沙箱失败", exc_info=True)
            queued_out = isinstance(exc, SandboxQueueTimeoutError)
            # 只有资源不足值得重试。其余按未分类错误处理 —— 盲目重试只是再炸一次，
            # 还多花一份 token
            code = RunErrorCode.SANDBOX_QUEUE_TIMEOUT if queued_out else RunErrorCode.INTERNAL
            await self._fail(run, code, str(exc), retryable=queued_out)
            return False

        await self._emit(SandboxReadyEvent(ts=now_ms(), run_id=run.id, path=(), data=SandboxReadyData()))
        return True

    async def _consume(self, run: Run, task: RunTask) -> None:
        """消费智能体的流，逐个 chunk 映射成事件。"""
        backend = self._backend(run.thread_id)
        tokens = TokenUsage()
        # 产物按 mtime 判定，基准要在 agent 动手之前取，否则本次的产出会被漏掉
        started_at = time.time_ns()

        async for ns, mode, payload in self._start(backend, run, task):
            tokens = tokens + _token_usage(mode, payload)
            # **只在 step 边界上查**：`updates` 每个图节点吐一条，一次分析约三十几次，
            # 那是可以干净停下的位置。逐个 token 去查是几千次 Redis 往返，
            # 而且停在模型调用中间也省不下什么 —— 那次调用的 token 已经花掉了
            if mode == UPDATES_MODE and await self._cancel.is_raised(run.id):
                await self._stop(run, tokens)
                raise RunCancelledError
            for event in map_chunk(ns, mode, payload, run_id=run.id):
                await self._log.append(event)

        # **流自然结束不等于跑完了**：中断会让执行暂停、流跟着结束，因此要回头查一次
        # 图状态。查状态而不是查流，是因为它两套 stream API 都成立，
        # 不依赖「某个模式会不会吐出中断」这个框架未确认的行为
        if await self._suspend(backend, run, tokens):
            return

        # 先落库再发终态事件：订阅方收到 run.finished 就会回头查 GET /runs/{id}，
        # 反过来的话那一查会读到还在 running。
        #
        # **落库失败就不发事件**：那意味着这个 run 已经有终态了 —— 教师在最后一刻点了
        # 停止，api 抢先写下 cancelled 并推过事件。这时再推一条 run.finished，
        # 前端会把一次被取消的分析显示成正常完成
        if not await self._repository.succeed(run.id, tokens=tokens):
            logger.info("run 已经有终态了，不再推 run.finished")
            return
        await self._emit(
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

    def _start(self, backend: BackendProtocol, run: Run, task: RunTask) -> AsyncIterator[StreamChunk]:
        """开跑或续跑。带着决策来的就是续跑，从中断点接着走。"""
        if task.decisions is None:
            return self._agent.stream(backend, run.thread_id, task.content)
        return self._agent.resume(backend, run.thread_id, to_resume(task.decisions))

    async def _suspend(self, backend: BackendProtocol, run: Run, tokens: TokenUsage) -> bool:
        """流结束后查一次中断；有就转 `waiting_approval` 并推 `interrupt`。

        Returns:
            是否停在了等人确认上。
        """
        actions = await self._agent.pending(backend, run.thread_id)
        if not actions:
            return False
        if await self._repository.wait_approval(run.id, tokens=tokens):
            await self._emit(InterruptEvent(ts=now_ms(), run_id=run.id, path=(), data=InterruptData(actions=actions)))
            logger.info("run 停在等人确认上：待确认 %d 个调用", len(actions))
        return True

    async def _stop(self, run: Run, tokens: TokenUsage) -> None:
        """落终态并推 `run.cancelled`。

        **状态先改、事件后推，而且只有改成了才推**：条件更新是原子的，api 那一侧
        可能已经抢先改过 —— 那时它已经推过事件了，这里再推一条，教师会看到两次「已取消」。
        """
        if await self._repository.cancel(run.id, tokens=tokens):
            await self._emit(
                RunCancelledEvent(ts=now_ms(), run_id=run.id, path=(), data=RunCancelledData(tokens=tokens))
            )

    async def _fail(self, run: Run, code: RunErrorCode, message: str, *, retryable: bool) -> None:
        # 同上：已经有终态就不再推事件
        if not await self._repository.fail(run.id, code=code, message=message or code.value):
            logger.info("run 已经有终态了，不再推 run.failed")
            return
        await self._emit(
            RunFailedEvent(
                ts=now_ms(),
                run_id=run.id,
                path=(),
                data=RunFailedData(code=code, message=message or code.value, retryable=retryable),
            )
        )

    async def _emit(self, event: Event) -> None:
        await self._log.append(event)


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
