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

from app.sandbox.path import SANDBOX_ROOT

logger = logging.getLogger(__name__)

DEFAULT_IMAGE = "zuel-sandbox:latest"

# 非 root 运行时容器内没有可写的家目录，matplotlib 与 pip 会把告警刷进 stdout，
# 混进 execute 的返回值里 —— agent 会把告警当成执行出错。指到 tmpfs 上消掉。
CONTAINER_TMP = "/tmp"
CONTAINER_HOME = CONTAINER_TMP
MPL_CONFIG_DIR = "/tmp/mpl"

# agent 自己装的包落在这里 —— 加固清单下**唯一既可写又可执行**的路径。
# rootfs 只读，而 HOME 所在的 /tmp 是 noexec 的 512m tmpfs：带原生扩展的包在那儿
# 装得下也加载不起来（scipy 的 .so 直接 ImportError），装得多了还会撑爆宿主内存。
# 落在 workspace 另有两个好处：被 5g XFS 配额兜住，且随会话持久，同一会话不必重装。
USER_BASE = f"{SANDBOX_ROOT}/.local"

# pip 缓存同样要躲开 /tmp —— 那是计入沙箱 2g 内存预算的 tmpfs，装一次 scipy 就是 45 MB。
PIP_CACHE_DIR = f"{SANDBOX_ROOT}/.cache/pip"

# 默认走清华源。实测直连 pypi.org 是 83 KB/s（scipy 一个包就要九分钟，必然撞上执行超时），
# 换镜像源后同样的包 14 秒 —— 对内网部署这是可用性问题，不是优化。
DEFAULT_INDEX_URL = "https://pypi.tuna.tsinghua.edu.cn/simple"

# 容器要长驻等后续调用，而不是跑完一条命令就退出
KEEP_ALIVE_COMMAND = ("sleep", "infinity")

# docker CLI 自身的超时。管的是 docker 客户端卡住，与容器内命令的超时无关
DOCKER_CLI_TIMEOUT = 30

# 容器上的标记。broker 重启后靠它把还在跑的沙箱认回来 —— 容器带 --rm 但**不是
# broker 的子进程**，broker 崩溃不会带走它们，不认领就是既占着内存又不在账上的孤儿。
MANAGED_LABEL = "zuel.sandbox"
THREAD_LABEL = "zuel.thread"

DEFAULT_RUNTIME = "runsc"
DEFAULT_NETWORK = "bridge"
DEFAULT_MEMORY = "2g"
DEFAULT_CPUS = "1"
DEFAULT_PIDS_LIMIT = 128
DEFAULT_TMP_SIZE = "512m"

# 沙箱共同的父 cgroup。**总量只能设在这里** —— 每个沙箱的 `--memory` 是各自独立的
# 天花板，20 个 2g 加起来 40g，没有任何东西拦着它们同时吃到，撑爆的是宿主机物理内存。
# 那时触发的是内核的全局 OOM，按 oom_score 在全机进程里挑最大的杀，很可能是 postgres
# 或 worker 而不是肇事的沙箱 —— 症状是「数据库莫名重启」，完全不指向真凶。
# 父节点的 memory.max 把这个爆炸半径关在沙箱这棵子树内，由 script/deploy.sh 设置。
# **slice 不存在时 Docker 自建一个不设限的**，因此没跑过部署脚本的机器行为不变。
DEFAULT_CGROUP_PARENT = "zuel-sandbox.slice"

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

# 沙箱被整个掀掉时的两种痕迹。gVisor 撞上内存或 pids 限额不是让 malloc/fork 失败，
# 而是直接终止整个沙箱：runsc 下 docker CLI 吐一句 `urpc method ... WaitPID failed`，
# runc 下则是进程收 SIGKILL（128+9）。
# **这段术语原样交给 LLM 就是噪音** —— 它读不出是超限，最可能当成平台抖动原样重试，
# 再撞一次同样的墙。换成人话它才知道该改写代码。
#
# 判据刻意不用 `docker inspect` 的 OOMKilled：那个标志**一旦置上就不会复位**，
# 而沙箱按 thread 复用半小时，据它翻译会让这个会话之后每一次普通报错都被说成内存超限。
GVISOR_TERMINATION_MARKER = "urpc method"
SIGKILL_EXIT_CODE = 137
SANDBOX_KILLED_MESSAGE = (
    "沙箱被强制终止 —— 通常是内存超过限额，或进程数超限。"
    "请分批处理数据、及时释放不再用的大对象，或减少并发的子进程后重试。"
)


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
    # 内存 + swap 的合计上限。留空则等于 `memory`，即**不许借 swap**。
    # Docker 的默认是给等量 swap（合计两倍），那会让沙箱在限额之外还能再借一份 ——
    # 实测借到之后同一个负载慢 2.7 倍，而单次执行只有 120 秒，减速会把它推向超时，
    # 症状「跑了两分钟没结果」不指向内存。且父 cgroup 的总量只管内存，swap 是账外的。
    memory_swap: str | None = None
    cpus: str = DEFAULT_CPUS
    pids_limit: int = DEFAULT_PIDS_LIMIT
    tmp_size: str = DEFAULT_TMP_SIZE
    # 沙箱共同的父 cgroup，内存总量设在它上面，见 DEFAULT_CGROUP_PARENT
    cgroup_parent: str = DEFAULT_CGROUP_PARENT
    # 沙箱以谁的身份跑，形如 "1000:1000"。留空则取当前进程的 uid:gid。
    # **broker 进容器之后当前进程是 root**，那时这个值必须显式给成宿主用户 ——
    # 否则 agent 写出的文件是 root 属主，宿主侧读不了，且症状不指向权限。
    user: str | None = None


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

    def adopt(self, container_id: str) -> None:
        """接管一个已经在跑的容器，不新起。

        Args:
            container_id: 已存在的容器标识。
        """
        ...


class DockerContainer:
    """跑在 gVisor 上的沙箱容器，一个 thread 一个。

    Args:
        thread_id: 会话标识，作为容器 label 打上去，broker 重启后靠它认领。
        workspace: 该 thread 在宿主机上的 workspace 目录，会挂进容器的 `/workspace`。
        image: 沙箱镜像。
        hardening: 资源限额与隔离档位，不传则用默认值。
        index_url: agent 装包时用的 PyPI 索引源。
    """

    def __init__(
        self,
        thread_id: str,
        workspace: Path,
        image: str = DEFAULT_IMAGE,
        hardening: Hardening | None = None,
        index_url: str = DEFAULT_INDEX_URL,
    ) -> None:
        self._thread_id = thread_id
        self._workspace = workspace.resolve()
        self._image = image
        self._hardening = hardening or Hardening()
        self._index_url = index_url
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
                # 认领用的标记，见 MANAGED_LABEL 的说明
                "--label",
                f"{MANAGED_LABEL}=1",
                "--label",
                f"{THREAD_LABEL}={self._thread_id}",
                # gVisor。容器逃逸要先过它这一层，是整套隔离的根基
                f"--runtime={limit.runtime}",
                # 出网，让 agent 能自己装包。**gVisor 之外没有第二层网络管控** ——
                # 沙箱里的代码能把 workspace 的东西发到任意地址，这是开网换来装包能力的代价，
                # 前提是威胁模型里的用户是实名可信的内部教师（ADR-0002）。
                f"--network={limit.network}",
                *ALWAYS_ON_ARGUMENT,
                # HOME 指到这里，所以必须可写；noexec 挡的是往家目录落可执行文件。
                # tmpfs 吃的是宿主机内存而非磁盘，不限容一句 dd 就能把宿主机写到 OOM
                "--tmpfs",
                f"{CONTAINER_TMP}:rw,noexec,nosuid,size={limit.tmp_size}",
                f"--memory={limit.memory}",
                # 与 memory 相等即关掉 swap，见 Hardening.memory_swap
                f"--memory-swap={limit.memory_swap or limit.memory}",
                f"--cpus={limit.cpus}",
                f"--pids-limit={limit.pids_limit}",
                # 归到公共父节点下，总量才有地方设，见 DEFAULT_CGROUP_PARENT
                f"--cgroup-parent={limit.cgroup_parent}",
                # uid/gid 对齐宿主，否则容器写出的文件宿主侧读不了（架构 §8.5 的部署前提）
                "--user",
                limit.user or f"{os.getuid()}:{os.getgid()}",
                "-v",
                f"{self._workspace}:{SANDBOX_ROOT}",
                "-w",
                SANDBOX_ROOT,
                "-e",
                f"HOME={CONTAINER_HOME}",
                "-e",
                f"MPLCONFIGDIR={MPL_CONFIG_DIR}",
                "-e",
                f"PYTHONUSERBASE={USER_BASE}",
                "-e",
                f"PIP_CACHE_DIR={PIP_CACHE_DIR}",
                # 让漏写 `--user` 的 `pip install` 也装到 USER_BASE。不设的话它会去装
                # 只读的 rootfs，报错后 agent 多半改去装 /tmp —— 那儿 noexec，装完照样跑不起来
                "-e",
                "PIP_USER=1",
                # 两个都要给：实测 uv **完全忽略** PIP_INDEX_URL，只认 UV_INDEX_URL。
                # 少给一个，agent 用 `uv pip` 时就悄悄退回官方源，症状只是慢到超时
                "-e",
                f"PIP_INDEX_URL={self._index_url}",
                "-e",
                f"UV_INDEX_URL={self._index_url}",
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

    def adopt(self, container_id: str) -> None:
        """接管一个已经在跑的容器，不新起。

        Args:
            container_id: 已存在的容器标识。
        """
        self._container_id = container_id

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
        merged = output + completed.stderr
        if _sandbox_was_killed(merged, completed.returncode):
            # 整段换掉而不是追加：沙箱被掀掉时前面那些字节是半截的、对 LLM 没有价值的噪音
            merged = SANDBOX_KILLED_MESSAGE
        return CommandResult(output=merged, exit_code=completed.returncode)

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


def running_sandbox() -> dict[str, str]:
    """列出本机上还在跑的沙箱容器。

    只认自己打的 label，因此不会把机器上别的容器卷进来。

    Returns:
        `thread_id → 容器 id`。没有则为空。

    Raises:
        ContainerError: docker 调用失败。
    """
    output = _run_docker(
        [
            "ps",
            "--filter",
            f"label={MANAGED_LABEL}",
            "--format",
            f'{{{{.ID}}}}\t{{{{.Label "{THREAD_LABEL}"}}}}',
        ],
        timeout=DOCKER_CLI_TIMEOUT,
    )

    found: dict[str, str] = {}
    for line in output.splitlines():
        container_id, separator, thread_id = line.partition("\t")
        # 没有 thread label 的不认领：那是别人打了同名 label 的容器，动它是越界
        if separator and thread_id:
            found[thread_id] = container_id
    return found


def _sandbox_was_killed(output: str, exit_code: int) -> bool:
    """这次失败是不是「整个沙箱被掀掉」，而非命令自己报错退出。

    Args:
        output: 合并后的命令输出。
        exit_code: 命令退出码。

    Returns:
        是则 True。
    """
    if exit_code == 0:
        return False
    return GVISOR_TERMINATION_MARKER in output or exit_code == SIGKILL_EXIT_CODE


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
