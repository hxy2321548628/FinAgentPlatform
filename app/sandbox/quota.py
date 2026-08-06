"""workspace 的磁盘配额：每个 thread 一份硬上限，用 XFS project quota。

加固清单里的 `--read-only` 只保护 rootfs，而 `/workspace` 是可写的 bind mount ——
LLM 生成的代码可以往里写满宿主机磁盘。这是威胁表「写满磁盘」那一格唯一没堵上的缺口。

**配额对目录生效而非对容器生效**，这正是选它的原因：文件工具是直接写宿主目录、
不进容器的，绕开了一切容器级限制，而目录配额照样管得住。
"""

import logging
import shlex
import subprocess
import zlib
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)

DEFAULT_DISK_QUOTA = "5g"

# xfs_quota 要 CAP_SYS_ADMIN。broker 容器内以 root 跑时留空即可，
# 开发机上平台是普通用户，要靠一条只放行 xfs_quota 的 NOPASSWD sudo 规则。
DEFAULT_QUOTA_COMMAND = ("xfs_quota",)

QUOTA_CLI_TIMEOUT = 30

# projid 0 是「不属于任何 project」，不能用。上界取 2^31-1 避开各种工具对
# 高位 id 的特殊处理，也给运维手工分配的 id 留出整个高半区。
PROJECT_ID_SPACE = 0x7FFFFFFF


class QuotaError(RuntimeError):
    """配额没能设上。

    不吞掉：设不上就等于这个 thread 能写满宿主机磁盘，而这正是 ADR-0015 要堵的洞。
    """


class QuotaProtocol(Protocol):
    """workspace 目录的配额分配。"""

    def assign(self, thread_id: str, workspace: Path) -> None:
        """给一个 thread 的 workspace 目录设上硬上限。

        Args:
            thread_id: 会话标识。
            workspace: 该会话在宿主机上的目录，需已存在。

        Raises:
            QuotaError: 配额没能设上。
        """
        ...


def project_id(thread_id: str) -> int:
    """由 thread_id 确定性派生出 projid。

    **不引入任何持久化状态**：本期没有 Postgres（P2 才上），ADR-0015 说的
    「`sandboxes` 表加一列」这个落点还不存在。另外两个方案 —— broker 内存表加
    启动时从 `xfs_quota report` 反查恢复、或落一个 JSON 文件 —— 都是给一个 P2
    就要拆掉的东西引入状态。

    碰撞的后果温和：两个 thread 共享一份 5GB 配额，是容量问题不是越权问题。
    P2 换成表时是纯替换。

    Args:
        thread_id: 会话标识。

    Returns:
        1 到 2^31-1 之间的 project id。
    """
    return zlib.crc32(thread_id.encode()) % PROJECT_ID_SPACE + 1


class XfsQuota:
    """用 XFS project quota 给 workspace 目录设硬上限。

    要求承载 workspace 的文件系统是 XFS 且以 `prjquota` 挂载 —— 这是一条部署前提，
    挂载选项改动要重启，事后补代价高。开发机上用 `deploy/setup-xfs.sh` 造。

    Args:
        mount_point: 承载各会话目录的 XFS 挂载点。
        limit: 每个 thread 的硬上限，`xfs_quota` 的 `bhard` 值。
        command: `xfs_quota` 的调用方式，用于在前面补上 `sudo`。
    """

    def __init__(
        self,
        *,
        mount_point: Path,
        limit: str = DEFAULT_DISK_QUOTA,
        command: Sequence[str] = DEFAULT_QUOTA_COMMAND,
    ) -> None:
        self._mount_point = mount_point
        self._limit = limit
        self._command = tuple(command)

    def assign(self, thread_id: str, workspace: Path) -> None:
        """给一个 thread 的 workspace 目录设上硬上限。

        重复调用是安全的：两条子命令都是幂等的赋值，容器销毁重建后再调一次也不会出错。

        Args:
            thread_id: 会话标识。
            workspace: 该会话在宿主机上的目录，需已存在。

        Raises:
            QuotaError: 配额没能设上。
        """
        identifier = project_id(thread_id)
        # 先认领目录再设限额。反过来的话，限额会先落在一个还没有任何目录的
        # project 上，中间那一小段时间里新建的文件不受任何约束
        self._run(f"project -s -p {shlex.quote(str(workspace))} {identifier}")
        self._run(f"limit -p bhard={self._limit} {identifier}")

    def _run(self, subcommand: str) -> None:
        argument = [*self._command, "-x", "-c", subcommand, str(self._mount_point)]
        try:
            subprocess.run(argument, capture_output=True, text=True, timeout=QUOTA_CLI_TIMEOUT, check=True)
        except subprocess.CalledProcessError as exc:
            message = f"设置配额失败（{subcommand}）：{exc.stderr.strip()}"
            raise QuotaError(message) from exc
        except subprocess.TimeoutExpired as exc:
            message = f"设置配额超时（{subcommand}）"
            raise QuotaError(message) from exc
        except OSError as exc:
            message = f"调不起 xfs_quota：{exc}"
            raise QuotaError(message) from exc


class NoQuota:
    """不设配额。

    **不是一个可以带进生产的选项** —— 它把「写满宿主机磁盘」这条路原样敞着。
    存在的理由只有一个：CI 与没挂 XFS 的开发机上，平台仍然要能跑起来。
    """

    def assign(self, thread_id: str, workspace: Path) -> None:
        """什么都不做。"""
