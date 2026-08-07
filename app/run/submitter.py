"""提交一次分析：记一行 run，投一条任务。

**这是 api 进程里与 run 有关的全部。** 执行在 worker 那边，两侧的交界就是那条任务消息。
`submit` 只做两件事，且顺序不能反 —— 先落库再投递，反过来的话 worker 可能抢在
`runs` 行写进去之前就开始改它的状态。
"""

import logging
from typing import Protocol
from uuid import uuid4

from event.model import RunStatus
from log import run_context
from run.repository import Run
from task.queue import RunTask, TaskQueue

logger = logging.getLogger(__name__)


class RunCreatorProtocol(Protocol):
    """提交侧对仓储的全部要求：只有建一行。

    查状态是端点的事，改状态是 worker 的事，都不经过这里。
    """

    async def create(self, *, run_id: str, thread_id: str) -> None:
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

    async def submit(self, *, thread_id: str, content: str) -> Run:
        """接下一次提问并立刻返回，执行由 worker 进行。

        Args:
            thread_id: 提问所属的会话。
            content: 教师的问题。

        Returns:
            状态为 `queued` 的 run 记录，`id` 用于订阅事件与查询状态。
        """
        run = Run(id=uuid4().hex, thread_id=thread_id, status=RunStatus.QUEUED)
        # 执行搬到 worker 之后，api 进程里关于一个 run 就只剩这一段。不绑身份的话，
        # 「按 run_id 把一次 run 的日志过滤出来」在 api 侧恒为空
        with run_context(run_id=run.id, thread_id=run.thread_id):
            await self._repository.create(run_id=run.id, thread_id=run.thread_id)
            await self._queue.publish(RunTask(run_id=run.id, thread_id=run.thread_id, content=content))
            logger.info("run 已投递")
        return run
