"""网关运行时依赖的一组长生命周期对象，以及它们的装配。

这些对象**每个进程只有一份**，随应用启动建立、随关闭销毁。集中在这里而不是散落成
模块级单例，是为了让测试能整份换掉，也为了让「谁依赖谁」在一个地方看得清。
"""

from dataclasses import dataclass

from fastapi import Request
from langgraph.checkpoint.memory import InMemorySaver

from agent.factory import create_model, create_runner
from config import Settings
from run.executor import RunExecutor
from run.log import EventLog
from sandbox.pool import SandboxPool
from sandbox.workspace import Workspace


@dataclass(frozen=True)
class Platform:
    """网关持有的运行时。"""

    workspace: Workspace
    pool: SandboxPool
    log: EventLog
    executor: RunExecutor


def build_platform(settings: Settings) -> Platform:
    """按配置装配一整套运行时。

    Args:
        settings: 平台配置。

    Returns:
        可直接交给应用使用的运行时。
    """
    workspace = Workspace(root=settings.sandbox_workspace_root)
    pool = SandboxPool(
        workspace_root=settings.sandbox_workspace_root,
        image=settings.sandbox_image,
        max_container=settings.sandbox_max_container,
        idle_timeout=settings.sandbox_idle_timeout,
        queue_timeout=settings.sandbox_queue_timeout,
    )
    log = EventLog()
    executor = RunExecutor(
        pool=pool,
        workspace=workspace,
        log=log,
        # checkpointer 是内存实现：进程重启后会话历史全丢，这笔债登记在 P2
        runner=create_runner(model=create_model(settings), checkpointer=InMemorySaver()),
    )
    return Platform(workspace=workspace, pool=pool, log=log, executor=executor)


def get_platform(request: Request) -> Platform:
    """路由取运行时的依赖项。"""
    platform: Platform = request.app.state.platform
    return platform
