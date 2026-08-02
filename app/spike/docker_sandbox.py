"""spike 用的最小 Docker 沙箱后端。

**不是 P1 的加固实现**（没有 gVisor、没有资源限制、没有网络白名单、没有磁盘配额），
唯一目的是让探针 2 跑真实分析时，LLM 生成的代码不落在宿主机上执行。

实现方式：继承 `BaseSandbox`，只补它的 4 个抽象成员。
文件传输直接读写 bind-mount 的宿主目录（对应 03agent-design §4.2 的路径映射），
其余文件操作沿用 BaseSandbox 默认实现 —— 它们会转成 shell 命令进容器执行。
"""

from __future__ import annotations

import os
import subprocess
import uuid
from pathlib import Path

from deepagents.backends.protocol import (
    FILE_NOT_FOUND,
    ExecuteResponse,
    FileDownloadResponse,
    FileUploadResponse,
)
from deepagents.backends.sandbox import BaseSandbox

SANDBOX_ROOT = "/workspace"
DEFAULT_TIMEOUT = 120


class DockerSandbox(BaseSandbox):
    """把一个长驻容器包成 SandboxBackendProtocol。用 with 语句管生命周期。"""

    def __init__(self, workspace: Path, image: str = "zuel-spike-sandbox:latest") -> None:
        self.workspace = workspace.resolve()
        self.image = image
        self._container_id: str | None = None
        # uid 对齐：容器内进程写出的文件，宿主侧（这里是 worker 进程）要能读写。
        # 架构文档 §8.5 把它列为部署前提，这里顺带验证一次。
        self._user = f"{os.getuid()}:{os.getgid()}"

    # ---------------------------------------------------------- 生命周期
    def __enter__(self) -> "DockerSandbox":
        self.workspace.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            [
                "docker", "run", "-d", "--rm",
                "--user", self._user,
                "-v", f"{self.workspace}:{SANDBOX_ROOT}",
                "-w", SANDBOX_ROOT,
                # 非 root 运行时容器内没有可写的 HOME，matplotlib/pip 会往 stdout 刷告警，
                # 混进 execute 的输出里干扰 LLM。指到 /tmp 消掉。
                "-e", "HOME=/tmp",
                "-e", "MPLCONFIGDIR=/tmp/mpl",
                self.image,
                "sleep", "infinity",
            ],
            capture_output=True, text=True, check=True,
        )
        self._container_id = proc.stdout.strip()
        return self

    def __exit__(self, *exc: object) -> None:
        if self._container_id:
            subprocess.run(["docker", "rm", "-f", self._container_id], capture_output=True, check=False)
            self._container_id = None

    # ------------------------------------------------ SandboxBackendProtocol
    @property
    def id(self) -> str:
        if not self._container_id:
            raise RuntimeError("沙箱未启动")
        return self._container_id

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        try:
            proc = subprocess.run(
                ["docker", "exec", "-w", SANDBOX_ROOT, self.id, "sh", "-c", command],
                capture_output=True, text=True, timeout=timeout or DEFAULT_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            # §3.4：错误要返回，不能抛 —— 抛异常会让整个 run 失败，而不是让 LLM 自己重试
            return ExecuteResponse(output=f"命令超时（{timeout or DEFAULT_TIMEOUT}s）", exit_code=124)
        return ExecuteResponse(output=proc.stdout + proc.stderr, exit_code=proc.returncode)

    # 文件传输走 bind-mount 宿主侧，不进容器
    def _host_path(self, sandbox_path: str) -> Path:
        relative = sandbox_path.removeprefix(SANDBOX_ROOT).lstrip("/")
        resolved = (self.workspace / relative).resolve()
        # 挡 ../ 穿越。agent 传来的路径是 LLM 生成的，属不可信输入（03agent-design §4.4）
        if not resolved.is_relative_to(self.workspace):
            raise ValueError(f"路径越界：{sandbox_path}")
        return resolved

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        responses = []
        for path, content in files:
            try:
                host = self._host_path(path)
                host.parent.mkdir(parents=True, exist_ok=True)
                host.write_bytes(content)
                responses.append(FileUploadResponse(path=path))
            except Exception as exc:  # noqa: BLE001
                responses.append(FileUploadResponse(path=path, error=str(exc)))
        return responses

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        responses = []
        for path in paths:
            try:
                host = self._host_path(path)
                responses.append(FileDownloadResponse(path=path, content=host.read_bytes()))
            except FileNotFoundError:
                responses.append(FileDownloadResponse(path=path, error=FILE_NOT_FOUND))
            except Exception as exc:  # noqa: BLE001
                responses.append(FileDownloadResponse(path=path, error=str(exc)))
        return responses


def image_exists(image: str) -> bool:
    proc = subprocess.run(["docker", "image", "inspect", image], capture_output=True, check=False)
    return proc.returncode == 0


def build_image(image: str = "zuel-spike-sandbox:latest") -> None:
    dockerfile = Path(__file__).parent / "Dockerfile.sandbox"
    print(f"构建镜像 {image} …")
    subprocess.run(
        ["docker", "build", "-f", str(dockerfile), "-t", image, str(dockerfile.parent)],
        check=True,
    )


if __name__ == "__main__":
    build_image()
    with DockerSandbox(Path(f"/tmp/zuel-spike-{uuid.uuid4().hex[:8]}")) as sbx:
        print("container:", sbx.id[:12])
        print(sbx.execute("python -c 'import pandas, matplotlib; print(pandas.__version__, matplotlib.__version__)'"))
