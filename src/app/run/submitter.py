"""提交一次分析：记一行 run，投一条任务。

**这是 api 进程里与 run 有关的全部。** 执行在 worker 那边，两侧的交界就是那条任务消息。
`submit` 只做两件事，且顺序不能反 —— 先落库再投递，反过来的话 worker 可能抢在
`runs` 行写进去之前就开始改它的状态。
"""

import logging
from typing import Protocol
from uuid import uuid4

from app.agent.config import AgentConfig
from app.agent.user_context import UserContext
from app.event.model import RunStatus
from app.run.decision import Decision
from app.run.repository import Run
from app.task.queue import RunTask, TaskQueue
from log import run_context

logger = logging.getLogger(__name__)


class RunCreatorProtocol(Protocol):
    """提交侧对仓储的全部要求：只有建一行。

    查状态是端点的事，改状态是 worker 的事，都不经过这里。
    """

    async def create(
        self,
        *,
        run_id: str,
        thread_id: str,
        user_id: str,
        content: str | None = None,
        agent_config: dict[str, object] | None = None,
        user_context: dict[str, object] | None = None,
    ) -> None:
        """记下一个刚提交的 run。"""
        ...


class RunSubmitter:
    """把一次提问变成一行 run 与一条任务。

    Args:
        repository: run 元数据的仓储。
        queue: 任务队列。
    """

    def __init__(self, *, repository: RunCreatorProtocol, queue: TaskQueue) -> None:
        self._repository = repository
        self._queue = queue

    async def submit(
        self,
        *,
        thread_id: str,
        content: str,
        user_id: str,
        agent_config: AgentConfig,
        user_context: UserContext | None = None,
    ) -> Run:
        """接下一次提问并立刻返回，执行由 worker 进行。

        **调用方必须先用同一个 `user_id` 查到这个 thread**：`runs.user_id` 与
        `threads.user_id` 的一致性就靠那一步，这里不再重查。

        **配置进来时已经是「这一轮实际生效的那一份」**：会话默认与本轮覆盖的取舍、
        以及 agent 引用的解析，都在端点那一层做完了。这一层只负责把它原样冻结下来 ——
        提交侧多一处能改配置的地方，就多一种「快照与实际跑的不是同一份」的失效。

        Args:
            thread_id: 提问所属的会话。
            content: 教师的问题。
            user_id: 提交的人。
            agent_config: 这一轮实际生效的配置，引用已解析。
            user_context: 提交时冻结的脱敏用户信息。

        Returns:
            状态为 `queued` 的 run 记录，`id` 用于订阅事件与查询状态。
        """
        effective = agent_config
        snapshot = effective.model_dump(exclude_none=True)
        run = Run(
            id=uuid4().hex,
            thread_id=thread_id,
            status=RunStatus.QUEUED,
            agent_config=effective,
            user_context=user_context,
        )
        # 执行搬到 worker 之后，api 进程里关于一个 run 就只剩这一段。不绑身份的话，
        # 「按 run_id 把一次 run 的日志过滤出来」在 api 侧恒为空
        with run_context(run_id=run.id, thread_id=run.thread_id, user_id=user_id):
            # 提问同时落库与入队。**两份不是冗余**：队列那份跑完就没了，
            # 而库里那份是聊天历史的用户那一侧 —— 没有它，翻看以前问过什么就无从谈起
            await self._repository.create(
                run_id=run.id,
                thread_id=run.thread_id,
                user_id=user_id,
                content=content,
                agent_config=snapshot,
                user_context=None if user_context is None else user_context.model_dump(mode="json"),
            )
            await self._queue.publish(
                RunTask(
                    run_id=run.id,
                    thread_id=run.thread_id,
                    content=content,
                    user_id=user_id,
                    user_context=user_context,
                    agent_config=effective,
                )
            )
            logger.info("run 已投递")
        return run

    async def resubmit(
        self,
        *,
        run_id: str,
        thread_id: str,
        user_id: str,
        decisions: list[Decision],
        agent_config: AgentConfig,
        user_context: UserContext | None = None,
    ) -> None:
        """审批之后把同一个 run 重新投一次。

        **不建新行**：`runs` 里那一行还是原来那个，只是状态从 `waiting_approval`
        回到了 `queued`。一次 run 因此会在队列里出现多次 —— 每轮审批一次。

        **不带教师的问题**：提问早就在 checkpoint 里了，重新发一遍只会让 agent
        以为又被问了一次。

        Args:
            run_id: 要续跑的 run。
            thread_id: 它所属的会话。
            user_id: 审批的人。
            decisions: 已经校验过的决策。
            agent_config: 原 run 提交时落下的配置快照。
            user_context: 原 run 提交时落下的脱敏用户快照。
        """
        with run_context(run_id=run_id, thread_id=thread_id, user_id=user_id):
            await self._queue.publish(
                RunTask(
                    run_id=run_id,
                    thread_id=thread_id,
                    user_id=user_id,
                    user_context=user_context,
                    decisions=decisions,
                    agent_config=agent_config,
                )
            )
            logger.info("审批已回传，run 重新入队续跑")
