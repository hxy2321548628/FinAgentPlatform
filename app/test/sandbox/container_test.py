"""需要真 Docker 与沙箱镜像的测试。

这里验证的东西没法用假对象替代：uid 对齐、bind-mount 双向可见、HOME 可写、
以及「容器停掉后七个文件工具仍然可用」—— 最后一条是不继承 BaseSandbox 的全部理由。
"""

import os
import shutil
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from sandbox.backend import SandboxBackend
from sandbox.container import DEFAULT_IMAGE, ContainerError, DockerContainer
from sandbox.path import OUTPUT_DIR


def _docker_ready() -> bool:
    if shutil.which("docker") is None:
        return False
    probe = subprocess.run(
        ["docker", "image", "inspect", DEFAULT_IMAGE],
        capture_output=True,
        check=False,
    )
    return probe.returncode == 0


pytestmark = pytest.mark.skipif(
    not _docker_ready(),
    reason=f"需要 docker 与镜像 {DEFAULT_IMAGE}（deploy/sandbox.Dockerfile）",
)


@pytest.fixture(scope="module")
def shared(tmp_path_factory: pytest.TempPathFactory) -> Iterator[DockerContainer]:
    """只读用途的共享容器 —— 起容器要一秒多，不必每个用例都来一次。"""
    workspace = tmp_path_factory.mktemp("shared-workspace")
    with DockerContainer(workspace=workspace) as container:
        yield container


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    space = tmp_path / "ws"
    space.mkdir()
    return space


def test_started_container_has_an_id(shared: DockerContainer) -> None:
    assert shared.id
    assert shared.started


def test_exec_returns_output_and_exit_code(shared: DockerContainer) -> None:
    result = shared.exec("echo hello", timeout=10)

    assert result.output == "hello\n"
    assert result.exit_code == 0


def test_exec_merges_stderr_into_the_output(shared: DockerContainer) -> None:
    """LLM 只看得到一段文本，报错必须在里面，否则它以为命令没输出。"""
    result = shared.exec("echo oops >&2", timeout=10)

    assert "oops" in result.output


def test_failing_command_reports_its_exit_code(shared: DockerContainer) -> None:
    result = shared.exec("exit 3", timeout=10)

    assert result.exit_code == 3


def test_exec_runs_inside_the_workspace(shared: DockerContainer) -> None:
    result = shared.exec("pwd", timeout=10)

    assert result.output.strip() == "/workspace"


def test_home_is_writable(shared: DockerContainer) -> None:
    """家目录不可写时 matplotlib 与 pip 会把告警刷进 stdout，agent 会当成执行出错。"""
    result = shared.exec("touch $HOME/probe && echo ok", timeout=10)

    assert result.output.strip() == "ok"
    assert result.exit_code == 0


def test_matplotlib_writes_no_warning_to_stdout(shared: DockerContainer) -> None:
    result = shared.exec("python -c 'import matplotlib.pyplot'", timeout=60)

    assert result.output == ""
    assert result.exit_code == 0


def test_chinese_labels_render_without_missing_glyphs(shared: DockerContainer) -> None:
    """中文字体缺失只会告警不会报错，agent 却会为此反复尝试联网找字体。"""
    script = (
        "import warnings; warnings.simplefilter('error');"
        "import matplotlib.pyplot as plt;"
        "plt.plot([1,2],[1,-2]); plt.title('年化波动率'); plt.savefig('/tmp/c.png')"
    )
    result = shared.exec(f'python -c "{script}"', timeout=60)

    assert result.exit_code == 0
    assert result.output == ""


def test_host_file_is_visible_inside_the_container(workspace: Path) -> None:
    (workspace / "data.csv").write_text("a,b\n", encoding="utf-8")

    with DockerContainer(workspace=workspace) as container:
        result = container.exec("cat data.csv", timeout=10)

    assert result.output == "a,b\n"


def test_container_output_is_owned_by_the_host_user(workspace: Path) -> None:
    """容器与宿主的 uid 不对齐会表现成「写得进、读不出」，而且症状不指向权限。"""
    with DockerContainer(workspace=workspace) as container:
        container.exec("echo x > written.txt", timeout=10)

    written = workspace / "written.txt"
    assert written.read_text(encoding="utf-8") == "x\n"
    assert written.stat().st_uid == os.getuid()


def test_timeout_raises_container_error(shared: DockerContainer) -> None:
    with pytest.raises(ContainerError):
        shared.exec("sleep 5", timeout=1)


def test_missing_image_raises_container_error(workspace: Path) -> None:
    """镜像没构建是最常见的部署疏漏，报错要指向镜像而不是一句 CalledProcessError。"""
    container = DockerContainer(workspace=workspace, image="zuel-nonexistent:v0")

    with pytest.raises(ContainerError, match="docker run 失败"):
        container.start()


def test_exec_before_start_raises_container_error(workspace: Path) -> None:
    container = DockerContainer(workspace=workspace)

    with pytest.raises(ContainerError):
        container.exec("echo hi", timeout=10)


def test_start_twice_keeps_the_same_container(workspace: Path) -> None:
    container = DockerContainer(workspace=workspace)
    try:
        container.start()
        first = container.id
        container.start()

        assert container.id == first
    finally:
        container.stop()


def test_stop_is_idempotent(workspace: Path) -> None:
    container = DockerContainer(workspace=workspace)
    container.start()

    container.stop()
    container.stop()

    assert not container.started


def test_workspace_is_created_when_missing(tmp_path: Path) -> None:
    """目录留给 Docker 创建会是 root 属主，容器以宿主 uid 运行就写不进去。"""
    absent = tmp_path / "not-yet" / "thread-1"

    with DockerContainer(workspace=absent) as container:
        result = container.exec("touch probe && echo ok", timeout=10)

    assert result.output.strip() == "ok"
    assert (absent / "probe").exists()


# ------------------------------------------------ backend 与容器的跨层验证
def test_file_tools_keep_working_after_the_container_stops(workspace: Path) -> None:
    """容器回收后翻看历史文件不该需要冷启动容器 —— 这正是不继承 BaseSandbox 的理由。"""
    container = DockerContainer(workspace=workspace)
    container.start()
    backend = SandboxBackend(workspace=workspace, container=container)
    backend.write("/workspace/data.csv", "a,b\n")

    container.stop()

    assert backend.read("/workspace/data.csv").error is None
    assert backend.ls("/workspace").error is None
    assert backend.glob("*.csv").error is None
    assert backend.grep("a").error is None
    assert backend.write("/workspace/new.txt", "y").error is None
    assert backend.edit("/workspace/new.txt", "y", "z").error is None
    assert backend.delete("/workspace/new.txt").error is None


def test_execute_after_the_container_stops_returns_error(workspace: Path) -> None:
    """只有 execute 依赖容器，它失败也只能返回错误而不是抛出。"""
    container = DockerContainer(workspace=workspace)
    container.start()
    backend = SandboxBackend(workspace=workspace, container=container)

    container.stop()
    response = backend.execute("echo hi")

    assert response.exit_code != 0
    assert "沙箱执行失败" in response.output


def test_agent_written_script_runs_in_the_container(workspace: Path) -> None:
    """write_file 写的脚本，execute 必须能直接跑 —— 两者在同一个命名空间。"""
    with DockerContainer(workspace=workspace) as container:
        backend = SandboxBackend(workspace=workspace, container=container)
        backend.write("/workspace/hello.py", "print('hello from sandbox')")

        response = backend.execute("python hello.py")

    assert response.exit_code == 0
    assert response.output.strip() == "hello from sandbox"


def test_chart_written_by_execute_is_detected_as_an_artifact(workspace: Path) -> None:
    with DockerContainer(workspace=workspace) as container:
        backend = SandboxBackend(workspace=workspace, container=container)
        backend.write(
            "/workspace/chart.py",
            "import matplotlib.pyplot as plt\n"
            "plt.plot([1, 2], [2, 1])\n"
            "plt.title('波动率')\n"
            f"plt.savefig('/workspace/{OUTPUT_DIR}/chart.png')\n",
        )
        since = time.time()
        response = backend.execute(f"mkdir -p {OUTPUT_DIR} && python chart.py", timeout=60)

    assert response.exit_code == 0
    assert [path.name for path in backend.artifact_since(since)] == ["chart.png"]
