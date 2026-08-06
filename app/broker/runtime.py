"""broker 持有的一组长生命周期对象，以及它们的装配。

**这个进程是唯一碰得到 `docker.sock` 与宿主 workspace 目录的地方。** api 进程被
agent 生成的内容影响之后，能做的最多是发几个 HTTP 请求过来，动不了容器、也动不了
别的会话的文件 —— 这正是把它拆出来的全部意义。
"""

import logging
from dataclasses import dataclass

from fastapi import Request

from config import Settings
from sandbox.backend import SandboxBackend
from sandbox.container import CommandResult, ContainerError
from sandbox.pool import SandboxPool
from sandbox.quota import NoQuota, QuotaProtocol, XfsQuota
from sandbox.workspace import Workspace

logger = logging.getLogger(__name__)


class AbsentContainer:
    """占位容器：这个 thread 眼下没有跑着的沙箱。

    七个文件工具直接读写宿主目录，容器在不在都照常可用；只有 `execute` 需要容器，
    它会在这里拿到一个错误并转成工具的 `error` 字段 —— 让 LLM 看到失败自己重试，
    好过抛异常把整个 run 打断。
    """

    @property
    def id(self) -> str:
        """容器标识。

        Raises:
            ContainerError: 没有容器可给。
        """
        message = "该会话当前没有运行中的沙箱"
        raise ContainerError(message)

    def exec(self, command: str, *, timeout: int) -> CommandResult:
        """执行命令，但这里根本没有容器。

        Raises:
            ContainerError: 总是抛。
        """
        message = "该会话当前没有运行中的沙箱，无法执行命令"
        raise ContainerError(message)


@dataclass(frozen=True)
class Broker:
    """broker 持有的运行时。"""

    workspace: Workspace
    pool: SandboxPool

    def backend(self, thread_id: str) -> SandboxBackend:
        """给一个 thread 组一个 backend。

        每次请求现组而不是长期持有：容器会被 LRU 淘汰、会因 OOM 消失、也会重建，
        缓存住一个 backend 就等于缓存住一个可能已经不在了的容器。

        Args:
            thread_id: 会话标识。

        Returns:
            该会话的文件空间与执行环境。
        """
        return SandboxBackend(
            workspace=self.workspace.path(thread_id),
            container=self.pool.current(thread_id) or AbsentContainer(),
        )


def build_broker(settings: Settings) -> Broker:
    """按配置装配 broker 的运行时。

    Args:
        settings: 平台配置。

    Returns:
        可直接交给路由使用的运行时。
    """
    workspace = Workspace(root=settings.sandbox_workspace_root, quota=_build_quota(settings))
    pool = SandboxPool(
        workspace=workspace,
        image=settings.sandbox_image,
        max_container=settings.sandbox_max_container,
        idle_timeout=settings.sandbox_idle_timeout,
        queue_timeout=settings.sandbox_queue_timeout,
        hardening=settings.hardening(),
    )
    return Broker(workspace=workspace, pool=pool)


def _build_quota(settings: Settings) -> QuotaProtocol:
    """按配置决定用不用磁盘配额。

    留空即关掉，且必须告警到日志里 —— 关掉之后「写满宿主机磁盘」这条路是敞着的，
    这种事不能只在配置文件里默默生效。
    """
    if not settings.sandbox_disk_quota:
        logger.warning("未设磁盘配额：单个会话可以写满宿主机磁盘。只有 CI 与没挂 XFS 的开发机才该这样跑")
        return NoQuota()
    return XfsQuota(
        mount_point=settings.sandbox_workspace_root,
        limit=settings.sandbox_disk_quota,
        command=settings.quota_command(),
    )


def get_broker(request: Request) -> Broker:
    """路由取运行时的依赖项。"""
    broker: Broker = request.app.state.broker
    return broker
