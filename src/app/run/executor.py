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
from collections.abc import AsyncIterator, Callable, Sequence
from typing import Protocol

from deepagents.backends.protocol import BackendProtocol
from langgraph.errors import GraphRecursionError

from app.agent.config import AgentConfig, SkillReference
from app.agent.factory import AgentSnapshot
from app.agent.user_context import UserContext
from app.event.mapper import EventMapper, StreamChunk
from app.event.model import (
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
    ToolCallEvent,
    ToolResultEvent,
    now_ms,
)
from app.memory.job import MemoryJobPayload, MemoryUsage, MemoryUsageStage
from app.memory.model import MemorySnapshot, UsageCallbackProtocol
from app.run.decision import to_resume
from app.run.log import EventLog, LoggedEvent
from app.run.repository import Run, RunStart
from app.sandbox.pool import SandboxQueueTimeoutError
from app.sandbox.remote import AsyncQueuePositionCallback, RemoteBackendFactory
from app.task.queue import RunTask
from log import run_context

logger = logging.getLogger(__name__)


class AgentProtocol(Protocol):
    """执行器对智能体的全部要求：开跑、恢复、问有没有在等人确认。

    编排框架的概念（graph、Command、checkpoint_ns）一个都不在这里 ——
    换掉框架时改的是装配层，不是执行器。
    """

    def stream(
        self,
        backend: BackendProtocol,
        thread_id: str,
        content: str,
        agent_config: AgentConfig,
        *,
        run_id: str,
        user_id: str | None = None,
        user_context: UserContext | None = None,
        selector_usage: UsageCallbackProtocol | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """第一次跑一个提问。

        `user_id` 只用于把这次执行归到人头上（追踪那一侧），不参与任何判断 ——
        授权在提交那一刻就做完了。
        """
        ...

    def resume(
        self,
        backend: BackendProtocol,
        thread_id: str,
        decisions: list[dict[str, object]],
        agent_config: AgentConfig,
        *,
        run_id: str,
        user_id: str | None = None,
        user_context: UserContext | None = None,
        selector_usage: UsageCallbackProtocol | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """带着教师的决策从中断点接着跑。"""
        ...

    async def inspect(
        self,
        backend: BackendProtocol,
        thread_id: str,
        run_id: str,
        agent_config: AgentConfig,
        *,
        user_context: UserContext | None = None,
    ) -> AgentSnapshot:
        """读取中断与成功 outbox 所需的受控消息。"""
        ...


# 按会话造 backend。注入进来而不是就地 new，是为了让测试能换掉传输层 ——
# 生产用发 HTTP 的远程实现，测试用直接读写临时目录的本地实现
type BackendFactory = Callable[[str], BackendProtocol]

UPDATES_MODE = "updates"


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

    async def start(self, run_id: str) -> RunStart:
        """标记开跑，并回答这一程是不是第一次开跑。"""
        ...

    async def succeed(
        self,
        run_id: str,
        *,
        tokens: TokenUsage,
        memory_job: MemoryJobPayload | None = None,
    ) -> bool:
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


class SkillAlignerProtocol(Protocol):
    """执行器对 Skill 存储层的全部要求：按快照全量对齐。"""

    async def align(self, thread_id: str, references: Sequence[SkillReference]) -> None:
        """把指定版本物化进会话 workspace。"""
        ...


class ThreadGuardProtocol(Protocol):
    """执行器在碰 workspace 前对 thread 生命周期的最后一道检查。"""

    async def active(self, thread_id: str, *, user_id: str) -> bool:
        """Thread 是否仍属于该用户且未软删。"""
        ...


class MemoryUsageRecorderProtocol(Protocol):
    """Executor 只向记忆账本写 selector 分项。"""

    async def record_usage(self, usage: MemoryUsage) -> None:
        """按 run/stage 幂等写入一条用量。"""
        ...


class MemoryCostProtocol(Protocol):
    """把 selector token 按明确模型换算为人民币。"""

    def yuan(self, model: str, tokens: TokenUsage) -> float:
        """返回这一次调用的成本。"""
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
        log: 事件日志，执行过程中产生的一切都往这里写。
        agent: 智能体，负责开跑、续跑与「有没有在等人确认」。
        repository: run 元数据的仓储，状态流转往这里落。
        backend_factory: 按会话造 backend，不传则发 HTTP 给 broker。
    """

    def __init__(
        self,
        *,
        pool: SandboxPoolProtocol,
        log: EventLog,
        agent: AgentProtocol,
        repository: RunRepositoryProtocol,
        cancel: CancelFlagProtocol,
        skill_aligner: SkillAlignerProtocol,
        thread_guard: ThreadGuardProtocol | None = None,
        backend_factory: BackendFactory | None = None,
        memory_usage: MemoryUsageRecorderProtocol | None = None,
        selector_model_name: str | None = None,
        selector_cost: MemoryCostProtocol | None = None,
    ) -> None:
        selector_ledger = (memory_usage, selector_model_name, selector_cost)
        if any(item is not None for item in selector_ledger) and not all(item is not None for item in selector_ledger):
            raise ValueError("selector 账本需同时配置仓储、模型名和单价")
        self._pool = pool
        self._backend = backend_factory or RemoteBackendFactory()
        self._log = log
        self._agent = agent
        self._repository = repository
        self._cancel = cancel
        self._skill_aligner = skill_aligner
        self._thread_guard = thread_guard
        self._memory_usage = memory_usage
        self._selector_model_name = selector_model_name
        self._selector_cost = selector_cost

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
        # 因此在这里绑定不会串到并发的其他 run 上。
        with run_context(run_id=run.id, thread_id=run.thread_id, user_id=user_id):
            # **开跑之前先看一眼**：取消一个还在排队的 run 时，任务消息仍然躺在队列里，
            # worker 迟早会领到它。不在这里挡一道，那次取消就只是把状态改了一下，
            # 而分析照跑不误 —— 那正是「取消没停下来」最典型的形态
            if await self._cancel.is_raised(run.id):
                logger.info("run 在开跑前已被取消，直接收手")
                await self._stop(run, TokenUsage())
                return

            # 删除先软删 DB、再让 broker 清 workspace。队列里的迟到任务仍可能在此后被领到；
            # 它不能先转成 running、推 run.started，更不能申请沙箱或把目录重新建回来。
            # 旧版队列消息没有 user_id，只对新消息启用这道 owner-aware 守卫。
            if (
                self._thread_guard is not None
                and user_id is not None
                and not await self._thread_guard.active(run.thread_id, user_id=user_id)
            ):
                logger.info("run 所属会话已删除，不再启动：thread_id=%s", run.thread_id)
                await self._stop(run, TokenUsage())
                return

            # 状态改不动就说明这个 run 已经走到终态了 —— 消息重投时会撞上这一条。
            # 硬跑下去等于让一次已经结束的分析又跑一遍，还多花一份 token
            start = await self._repository.start(run.id)
            if start is RunStart.REFUSED:
                logger.info("run 已经有终态了，这一次投递不再执行")
                return

            # `resumed` 的含义是**「这不是第一次开跑」**，两个来源缺一不可：
            #
            # - 带着决策来的是审批之后的续跑，而 `resume()` 已经把状态放回了 `queued`，
            #   光看状态与第一次开跑分不开；
            # - 状态已经是 `running` / `waiting_approval` 的，是崩溃或超时之后的重投，
            #   那一程不带决策。
            #
            # 崩溃恢复与审批续跑对前端是同一件事：**别把已经显示的对话重置**。
            resumed = task.decisions is not None or start is RunStart.RESUMED
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
                await self._align_skills(run, task.agent_config)
                await self._consume(run, task)
            except RunCancelledError:
                # 取消不是失败。沙箱在 finally 里归还，已经写入的 checkpoint 原样留着 ——
                # 那是「从该点还能续跑」的全部依据
                logger.info("run 已按教师的要求停下")
            # 跑飞要与「模型断连」分开记：教师对这两件事该做的处置不一样，
            # 而混在一起之后「这次分析是不是太复杂了」就永远查不出来
            except GraphRecursionError as exc:
                logger.warning("run 撞上递归上限", exc_info=True)
                await self._fail(run, RunErrorCode.RECURSION_LIMIT, str(exc), retryable=False)
            # 智能体那一侧什么都可能抛：模型断连、工具越界。宽捕获是刻意的 ——
            # 让异常逃出去只会让后台任务无声无息地死掉，订阅这个 run 的连接则永远等不到终态。
            except Exception as exc:
                logger.warning("run 执行失败", exc_info=True)
                await self._fail(run, RunErrorCode.INTERNAL, str(exc), retryable=False)
            finally:
                await self._pool.release(run.thread_id, holder=run.id)

    async def _align_skills(self, run: Run, config: AgentConfig) -> None:
        """有 Skill 时按冻结快照对齐；空配置不增加 Broker 往返。"""
        if not config.skills:
            return
        await self._skill_aligner.align(run.thread_id, config.skills)

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
        history = await self._log.read(run.id)
        mapper = EventMapper(run.id, known_tool_paths=_known_tool_paths(history))

        def selector_usage(usage: TokenUsage) -> None:
            nonlocal tokens
            tokens = tokens + usage

        async for ns, mode, payload in self._start(backend, run, task, selector_usage=selector_usage):
            tokens = tokens + _token_usage(mode, payload)
            # **只在 step 边界上查**：`updates` 每个图节点吐一条，一次分析约三十几次，
            # 那是可以干净停下的位置。逐个 token 去查是几千次 Redis 往返，
            # 而且停在模型调用中间也省不下什么 —— 那次调用的 token 已经花掉了
            if mode == UPDATES_MODE and await self._cancel.is_raised(run.id):
                await self._stop(run, tokens)
                raise RunCancelledError
            for event in mapper.map_chunk(ns, mode, payload):
                await self._log.append(event)

        # **流自然结束不等于跑完了**：中断会让执行暂停、流跟着结束，因此要回头查一次
        # 图状态。查状态而不是查流，是因为它两套 stream API 都成立，
        # 不依赖「某个模式会不会吐出中断」这个框架未确认的行为
        snapshot = await self._agent.inspect(
            backend,
            run.thread_id,
            run.id,
            task.agent_config,
            user_context=task.user_context,
        )
        await self._record_selector_usage(run, snapshot.memory)
        if await self._suspend(run, tokens, snapshot.actions):
            return

        # 先落库再发终态事件：订阅方收到 run.finished 就会回头查 GET /runs/{id}，
        # 反过来的话那一查会读到还在 running。
        #
        # **落库失败就不发事件**：那意味着这个 run 已经有终态了 —— 教师在最后一刻点了
        # 停止，api 抢先写下 cancelled 并推过事件。这时再推一条 run.finished，
        # 前端会把一次被取消的分析显示成正常完成
        memory_job = None
        if task.user_id is not None and snapshot.messages:
            memory_job = MemoryJobPayload(
                thread_id=run.thread_id,
                user_id=task.user_id,
                messages=snapshot.messages,
            )
        if not await self._repository.succeed(run.id, tokens=tokens, memory_job=memory_job):
            logger.info("run 已经有终态了，不再推 run.finished")
            return
        await self._emit(RunFinishedEvent(ts=now_ms(), run_id=run.id, path=(), data=RunFinishedData(tokens=tokens)))

    async def _record_selector_usage(self, run: Run, snapshot: MemorySnapshot | None) -> None:
        """把 selector 的可审计分项落账；失败不改写主 run 终态。"""
        if (
            snapshot is None
            or self._memory_usage is None
            or self._selector_model_name is None
            or self._selector_cost is None
        ):
            return
        usage = snapshot.selector_usage
        try:
            await self._memory_usage.record_usage(
                MemoryUsage(
                    run_id=run.id,
                    thread_id=run.thread_id,
                    stage=MemoryUsageStage.SELECTOR,
                    model=self._selector_model_name,
                    tokens=usage,
                    cost_yuan=self._selector_cost.yuan(self._selector_model_name, usage),
                    duration_ms=snapshot.selector_duration_ms,
                    hit_count=len(snapshot.records),
                    rejected_count=max(0, len(snapshot.selected_indices) - len(snapshot.records)),
                    fallback_reason=None if snapshot.fallback is None else snapshot.fallback.value,
                    included_in_run=True,
                    selected_slugs=snapshot.selected_slugs,
                )
            )
        except Exception:
            # 记账与记忆服务同样是附加链路：主分析已经产生了正常结果，
            # 不能因为这一行审计写失败就对教师改报 INTERNAL。
            logger.warning("selector 用量落账失败", exc_info=True)

    def _start(
        self,
        backend: BackendProtocol,
        run: Run,
        task: RunTask,
        *,
        selector_usage: UsageCallbackProtocol,
    ) -> AsyncIterator[StreamChunk]:
        """开跑或续跑。带着决策来的就是续跑，从中断点接着走。"""
        if task.decisions is None:
            return self._agent.stream(
                backend,
                run.thread_id,
                task.content,
                task.agent_config,
                run_id=run.id,
                user_id=task.user_id,
                user_context=task.user_context,
                selector_usage=selector_usage,
            )
        return self._agent.resume(
            backend,
            run.thread_id,
            to_resume(task.decisions),
            task.agent_config,
            run_id=run.id,
            user_id=task.user_id,
            user_context=task.user_context,
            selector_usage=selector_usage,
        )

    async def _suspend(
        self,
        run: Run,
        tokens: TokenUsage,
        actions: list[InterruptAction],
    ) -> bool:
        """流结束后查一次中断；有就转 `waiting_approval` 并推 `interrupt`。

        Returns:
            是否停在了等人确认上。
        """
        if not actions:
            return False
        if await self._repository.wait_approval(run.id, tokens=tokens):
            path = _pending_action_path(await self._log.read(run.id), actions)
            await self._emit(InterruptEvent(ts=now_ms(), run_id=run.id, path=path, data=InterruptData(actions=actions)))
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


def _known_tool_paths(history: Sequence[LoggedEvent]) -> dict[str, tuple[str, ...]]:
    """从不可变事件恢复 tool_call_id 到子图路径的映射，供审批续跑使用。"""
    return {
        event.data.id: event.path
        for logged in history
        if isinstance((event := logged.event), ToolCallEvent) and event.path
    }


def _pending_action_path(
    history: Sequence[LoggedEvent],
    actions: Sequence[InterruptAction],
) -> tuple[str, ...]:
    """用尚未完成的工具调用给 interrupt 补上子图路径。"""
    completed = {event.data.tool_call_id for logged in history if isinstance((event := logged.event), ToolResultEvent)}
    pending = [
        event
        for logged in history
        if isinstance((event := logged.event), ToolCallEvent) and event.data.id not in completed
    ]
    paths: list[tuple[str, ...]] = []
    used: set[str] = set()
    for action in actions:
        match = next(
            (
                event
                for event in reversed(pending)
                if event.data.id not in used and event.data.name == action.tool_name and event.data.args == action.args
            ),
            None,
        )
        if match is None:
            return ()
        used.add(match.data.id)
        paths.append(match.path)
    return paths[0] if paths and all(path == paths[0] for path in paths) else ()


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
