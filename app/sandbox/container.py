"""沙箱容器：backend 对容器的抽象，以及 Docker 上的实现。

容器是**可抛弃**的 —— 文件留在 bind-mount 的 workspace 里，销毁重建不丢东西。
只有 `execute` 需要容器在跑，七个文件工具直接操作宿主目录。
"""

import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Protocol

from sandbox.path import SANDBOX_ROOT

logger = logging.getLogger(__name__)

DEFAULT_IMAGE = "zuel-sandbox:latest"

# 非 root 运行时容器内没有可写的家目录，matplotlib 与 pip 会把告警刷进 stdout，
# 混进 execute 的返回值里 —— agent 会把告警当成执行出错。指到 tmpfs 上消掉。
CONTAINER_HOME = "/tmp"
MPL_CONFIG_DIR = "/tmp/mpl"

# 容器要长驻等后续调用，而不是跑完一条命令就退出
KEEP_ALIVE_COMMAND = ("sleep", "infinity")

# docker CLI 自身的超时。管的是 docker 客户端卡住，与容器内命令的超时无关
DOCKER_CLI_TIMEOUT = 30


@dataclass(frozen=True)
class CommandResult:
    """容器内一次命令执行的结果。"""

    output: str
    exit_code: int


class ContainerError(RuntimeError):
    """容器不可用，或命令没能正常跑完。

    由 backend 在边界捕获并转成工具的 `error` 字段 —— 抛到 LangGraph 会让整个 run 失败，
    而返回错误能让 LLM 自己改代码重试。
    """


class ContainerProtocol(Protocol):
    """backend 对容器的全部要求。

    刻意只有两个成员：七个文件工具直接操作宿主机上的 bind-mount 目录，
    只有 `execute` 需要容器。协议小，才能让「容器停掉文件工具照常可用」成立。
    """

    @property
    def id(self) -> str:
        """容器标识。"""
        ...

    def exec(self, command: str, *, timeout: int) -> CommandResult:
        """在容器内执行一条 shell 命令。

        Args:
            command: 完整的 shell 命令串。
            timeout: 超时秒数。

        Returns:
            命令的合并输出与退出码。

        Raises:
            ContainerError: 容器不可用、命令超时，或 docker 调用本身失败。
        """
        ...


class DockerContainer:
    """跑在 Docker 上的沙箱容器，一个 thread 一个。

    **不含 P1 的加固措施**（gVisor、只读 rootfs、网络隔离、资源限制）——
    P0 已把它们登记为不可跳过的欠债，这里只有一层容器边界。

    Args:
        workspace: 该 thread 在宿主机上的 workspace 目录，会挂进容器的 `/workspace`。
        image: 沙箱镜像。
    """

    def __init__(self, workspace: Path, image: str = DEFAULT_IMAGE) -> None:
        self._workspace = workspace.resolve()
        self._image = image
        self._container_id: str | None = None

    @property
    def id(self) -> str:
        """容器标识。

        Raises:
            ContainerError: 容器尚未启动。没 start 就用属于编程错误，不该静默返回空值。
        """
        if self._container_id is None:
            message = "容器尚未启动"
            raise ContainerError(message)
        return self._container_id

    @property
    def started(self) -> bool:
        """容器是否已启动。"""
        return self._container_id is not None

    def start(self) -> None:
        """启动容器，已启动则什么都不做。

        Raises:
            ContainerError: docker 启动失败。
        """
        if self._container_id is not None:
            return

        # bind-mount 的目标必须先存在：留给 Docker 创建会是 root 属主，
        # 而容器以宿主 uid 运行，写不进去
        self._workspace.mkdir(parents=True, exist_ok=True)
        output = _run_docker(
            [
                "run",
                "-d",
                "--rm",
                # 镜像必须是本地预先构建或导入的。不加这条，镜像名写错时 Docker 会去
                # registry 拉取，在内网里卡满整个超时才失败，且错误指向网络而非镜像。
                "--pull=never",
                # uid/gid 对齐宿主，否则容器写出的文件宿主侧读不了（架构 §8.5 的部署前提）
                "--user",
                f"{os.getuid()}:{os.getgid()}",
                "-v",
                f"{self._workspace}:{SANDBOX_ROOT}",
                "-w",
                SANDBOX_ROOT,
                "-e",
                f"HOME={CONTAINER_HOME}",
                "-e",
                f"MPLCONFIGDIR={MPL_CONFIG_DIR}",
                self._image,
                *KEEP_ALIVE_COMMAND,
            ],
            timeout=DOCKER_CLI_TIMEOUT,
        )
        self._container_id = output.strip()

    def stop(self) -> None:
        """销毁容器。未启动或已销毁时什么都不做。

        清理失败只记日志不抛 —— 调用方通常在收尾路径上，没有可做的补救。
        """
        if self._container_id is None:
            return

        try:
            _run_docker(["rm", "-f", self._container_id], timeout=DOCKER_CLI_TIMEOUT)
        except ContainerError:
            logger.warning("容器清理失败，可能有残留：%s", self._container_id, exc_info=True)
        finally:
            self._container_id = None

    def exec(self, command: str, *, timeout: int) -> CommandResult:
        """在容器内执行一条 shell 命令。

        Args:
            command: 完整的 shell 命令串，由容器内的 sh 解释。
            timeout: 超时秒数。

        Returns:
            合并后的 stdout 与 stderr，以及退出码。

        Raises:
            ContainerError: 容器未启动、命令超时，或 docker 调用失败。
        """
        try:
            completed = subprocess.run(
                ["docker", "exec", "-w", SANDBOX_ROOT, self.id, "sh", "-c", command],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            message = f"命令超时（{timeout} 秒）"
            raise ContainerError(message) from exc
        except OSError as exc:
            message = f"docker 调用失败：{exc}"
            raise ContainerError(message) from exc

        return CommandResult(output=completed.stdout + completed.stderr, exit_code=completed.returncode)

    def __enter__(self) -> "DockerContainer":
        """启动容器并返回自身。"""
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """离开上下文时销毁容器。"""
        self.stop()


def _run_docker(argument: list[str], *, timeout: int) -> str:
    """调一次 docker CLI，失败一律转成 ContainerError。"""
    try:
        completed = subprocess.run(
            ["docker", *argument],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        message = f"docker {argument[0]} 失败：{exc.stderr.strip()}"
        raise ContainerError(message) from exc
    except subprocess.TimeoutExpired as exc:
        message = f"docker {argument[0]} 超时（{timeout} 秒）"
        raise ContainerError(message) from exc
    except OSError as exc:
        message = f"docker 调用失败：{exc}"
        raise ContainerError(message) from exc

    return completed.stdout
