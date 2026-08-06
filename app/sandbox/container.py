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
CONTAINER_TMP = "/tmp"
CONTAINER_HOME = CONTAINER_TMP
MPL_CONFIG_DIR = "/tmp/mpl"

# 容器要长驻等后续调用，而不是跑完一条命令就退出
KEEP_ALIVE_COMMAND = ("sleep", "infinity")

# docker CLI 自身的超时。管的是 docker 客户端卡住，与容器内命令的超时无关
DOCKER_CLI_TIMEOUT = 30

DEFAULT_RUNTIME = "runsc"
DEFAULT_NETWORK = "none"
DEFAULT_MEMORY = "2g"
DEFAULT_CPUS = "1"
DEFAULT_PIDS_LIMIT = 128
DEFAULT_TMP_SIZE = "512m"

# 这三条**刻意不做成配置项**：它们没有「调小一点」的中间档，只有开和关，
# 而关掉就是直接开一个缺口。做成开关等于给一个配错了也不会有任何症状的失守留了入口。
ALWAYS_ON_ARGUMENT = (
    "--read-only",
    "--cap-drop=ALL",
    "--security-opt=no-new-privileges",
)

# 单次执行的输出上限。一句 `while True: print(x)` 在 120 秒超时内能刷出几个 GB，
# 原样收进网关就是一次 OOM。
OUTPUT_LIMIT_BYTE = 1 << 20
TRUNCATION_MARKER = "…[输出超过 1 MiB，已截断]"


@dataclass(frozen=True)
class Hardening:
    """沙箱的资源限额与隔离档位。

    整组一起传是刻意的：这些参数要么全生效、要么等于没设，而漏掉一条没有任何症状 ——
    散成六个参数摆在 `start()` 的签名里，写错一个要等到有人真的越出来才会发现。

    只收**有中间档的量**。`--read-only` 这类没有中间态的见 `ALWAYS_ON_ARGUMENT`。
    """

    runtime: str = DEFAULT_RUNTIME
    network: str = DEFAULT_NETWORK
    memory: str = DEFAULT_MEMORY
    cpus: str = DEFAULT_CPUS
    pids_limit: int = DEFAULT_PIDS_LIMIT
    tmp_size: str = DEFAULT_TMP_SIZE


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


class ManagedContainerProtocol(ContainerProtocol, Protocol):
    """沙箱池对容器的全部要求，比 backend 多出生命周期与健康探测。

    分成两个协议是刻意的：backend 只该知道「怎么执行命令」，
    什么时候起、什么时候销毁、还活着没有，都不是它的事。
    """

    def start(self) -> None:
        """启动容器，已启动则什么都不做。

        Raises:
            ContainerError: 启动失败。
        """
        ...

    def stop(self) -> None:
        """销毁容器。未启动或已销毁时什么都不做。"""
        ...

    def alive(self) -> bool:
        """容器是否仍在运行。"""
        ...


class DockerContainer:
    """跑在 gVisor 上的沙箱容器，一个 thread 一个。

    Args:
        workspace: 该 thread 在宿主机上的 workspace 目录，会挂进容器的 `/workspace`。
        image: 沙箱镜像。
        hardening: 资源限额与隔离档位，不传则用默认值。
    """

    def __init__(self, workspace: Path, image: str = DEFAULT_IMAGE, hardening: Hardening | None = None) -> None:
        self._workspace = workspace.resolve()
        self._image = image
        self._hardening = hardening or Hardening()
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
        limit = self._hardening
        output = _run_docker(
            [
                "run",
                "-d",
                "--rm",
                # 镜像必须是本地预先构建或导入的。不加这条，镜像名写错时 Docker 会去
                # registry 拉取，在内网里卡满整个超时才失败，且错误指向网络而非镜像。
                "--pull=never",
                # gVisor。容器逃逸要先过它这一层，是整套隔离的根基
                f"--runtime={limit.runtime}",
                # 零出网。装包因此不可能，这是「不部署 devpi」那个决策的另一半
                f"--network={limit.network}",
                *ALWAYS_ON_ARGUMENT,
                # HOME 指到这里，所以必须可写；noexec 挡的是往家目录落可执行文件。
                # tmpfs 吃的是宿主机内存而非磁盘，不限容一句 dd 就能把宿主机写到 OOM
                "--tmpfs",
                f"{CONTAINER_TMP}:rw,noexec,nosuid,size={limit.tmp_size}",
                f"--memory={limit.memory}",
                f"--cpus={limit.cpus}",
                f"--pids-limit={limit.pids_limit}",
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

    def alive(self) -> bool:
        """容器是否仍在运行。

        问的是 Docker 而不是自己的记录：容器可能被 OOM killer 干掉、被运维手动删掉，
        或因 `--rm` 在崩溃后自动消失，这些情况本进程都收不到通知。
        """
        if self._container_id is None:
            return False
        try:
            output = _run_docker(
                ["inspect", "-f", "{{.State.Running}}", self._container_id],
                timeout=DOCKER_CLI_TIMEOUT,
            )
        except ContainerError:
            # 容器已被删除时 inspect 直接失败，这与「没在跑」是同一个结论
            return False
        return output.strip() == "true"

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
                ["docker", "exec", "-w", SANDBOX_ROOT, self.id, "bash", "-o", "pipefail", "-c", _capped(command)],
                capture_output=True,
                text=True,
                # head -c 按字节切，可能把一个 UTF-8 汉字劈成两半，严格解码会在这里抛
                errors="replace",
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            message = f"命令超时（{timeout} 秒）"
            raise ContainerError(message) from exc
        except OSError as exc:
            message = f"docker 调用失败：{exc}"
            raise ContainerError(message) from exc

        output = completed.stdout
        if len(output.encode("utf-8", errors="replace")) >= OUTPUT_LIMIT_BYTE:
            # 不加标记的话，LLM 会把截断处当成程序的全部输出，据此推出错误的结论
            output += TRUNCATION_MARKER
        return CommandResult(output=output + completed.stderr, exit_code=completed.returncode)

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


def _capped(command: str) -> str:
    """把命令的输出在容器内就截到上限。

    截在容器里而不是拿回来再截：等它流过 docker CLI，网关已经把几个 GB 收进内存了。
    `head -c` 到量就关掉管道，写端下一次 write 拿到 SIGPIPE 自己就死了。

    用 `bash -o pipefail` 而非 `sh`，是因为管道的退出码默认取自 `head`（总是 0）——
    少了 pipefail，失败的命令会被报成成功，LLM 拿着错误的结论继续往下写。
    """
    return f"{{ {command}; }} 2>&1 | head -c {OUTPUT_LIMIT_BYTE}"


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
