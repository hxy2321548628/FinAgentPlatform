"""需要真 Docker 与沙箱镜像的测试。

这里验证的东西没法用假对象替代：uid 对齐、bind-mount 双向可见、HOME 可写、
以及「容器停掉后七个文件工具仍然可用」—— 最后一条是不继承 BaseSandbox 的全部理由。
"""

import os
import shlex
import shutil
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from sandbox.backend import SandboxBackend
from sandbox.container import (
    DEFAULT_IMAGE,
    OUTPUT_LIMIT_BYTE,
    TRUNCATION_MARKER,
    ContainerError,
    DockerContainer,
    Hardening,
    running_sandbox,
)
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

# 子进程必须活着不退，否则同时存在的进程数永远到不了上限，测的就不是 pids-limit
FORK_BOMB = """
import os, time
n = 0
while n < 300:
    if os.fork() == 0:
        time.sleep(20)
        os._exit(0)
    n += 1
"""


@pytest.fixture(scope="module")
def shared(tmp_path_factory: pytest.TempPathFactory) -> Iterator[DockerContainer]:
    """只读用途的共享容器 —— 起容器要一秒多，不必每个用例都来一次。"""
    workspace = tmp_path_factory.mktemp("shared-workspace")
    with DockerContainer(thread_id="test-thread", workspace=workspace) as container:
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

    with DockerContainer(thread_id="test-thread", workspace=workspace) as container:
        result = container.exec("cat data.csv", timeout=10)

    assert result.output == "a,b\n"


def test_container_output_is_owned_by_the_host_user(workspace: Path) -> None:
    """容器与宿主的 uid 不对齐会表现成「写得进、读不出」，而且症状不指向权限。"""
    with DockerContainer(thread_id="test-thread", workspace=workspace) as container:
        container.exec("echo x > written.txt", timeout=10)

    written = workspace / "written.txt"
    assert written.read_text(encoding="utf-8") == "x\n"
    assert written.stat().st_uid == os.getuid()


def test_timeout_raises_container_error(shared: DockerContainer) -> None:
    with pytest.raises(ContainerError):
        shared.exec("sleep 5", timeout=1)


def test_missing_image_raises_container_error(workspace: Path) -> None:
    """镜像没构建是最常见的部署疏漏，报错要指向镜像而不是一句 CalledProcessError。"""
    container = DockerContainer(thread_id="test-thread", workspace=workspace, image="zuel-nonexistent:v0")

    with pytest.raises(ContainerError, match="docker run 失败"):
        container.start()


def test_exec_before_start_raises_container_error(workspace: Path) -> None:
    container = DockerContainer(thread_id="test-thread", workspace=workspace)

    with pytest.raises(ContainerError):
        container.exec("echo hi", timeout=10)


def test_start_twice_keeps_the_same_container(workspace: Path) -> None:
    container = DockerContainer(thread_id="test-thread", workspace=workspace)
    try:
        container.start()
        first = container.id
        container.start()

        assert container.id == first
    finally:
        container.stop()


def test_stop_is_idempotent(workspace: Path) -> None:
    container = DockerContainer(thread_id="test-thread", workspace=workspace)
    container.start()

    container.stop()
    container.stop()

    assert not container.started


def test_workspace_is_created_when_missing(tmp_path: Path) -> None:
    """目录留给 Docker 创建会是 root 属主，容器以宿主 uid 运行就写不进去。"""
    absent = tmp_path / "not-yet" / "thread-1"

    with DockerContainer(thread_id="test-thread", workspace=absent) as container:
        result = container.exec("touch probe && echo ok", timeout=10)

    assert result.output.strip() == "ok"
    assert (absent / "probe").exists()


# ------------------------------------------------ backend 与容器的跨层验证
def test_file_tools_keep_working_after_the_container_stops(workspace: Path) -> None:
    """容器回收后翻看历史文件不该需要冷启动容器 —— 这正是不继承 BaseSandbox 的理由。"""
    container = DockerContainer(thread_id="test-thread", workspace=workspace)
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
    container = DockerContainer(thread_id="test-thread", workspace=workspace)
    container.start()
    backend = SandboxBackend(workspace=workspace, container=container)

    container.stop()
    response = backend.execute("echo hi")

    assert response.exit_code != 0
    assert "沙箱执行失败" in response.output


def test_agent_written_script_runs_in_the_container(workspace: Path) -> None:
    """write_file 写的脚本，execute 必须能直接跑 —— 两者在同一个命名空间。"""
    with DockerContainer(thread_id="test-thread", workspace=workspace) as container:
        backend = SandboxBackend(workspace=workspace, container=container)
        backend.write("/workspace/hello.py", "print('hello from sandbox')")

        response = backend.execute("python hello.py")

    assert response.exit_code == 0
    assert response.output.strip() == "hello from sandbox"


def test_chart_written_by_execute_is_detected_as_an_artifact(workspace: Path) -> None:
    with DockerContainer(thread_id="test-thread", workspace=workspace) as container:
        backend = SandboxBackend(workspace=workspace, container=container)
        backend.write(
            "/workspace/chart.py",
            "import matplotlib.pyplot as plt\n"
            "plt.plot([1, 2], [2, 1])\n"
            "plt.title('波动率')\n"
            f"plt.savefig('/workspace/{OUTPUT_DIR}/chart.png')\n",
        )
        since = time.time_ns()
        response = backend.execute(f"mkdir -p {OUTPUT_DIR} && python chart.py", timeout=60)

    assert response.exit_code == 0
    assert [path.name for path in backend.artifact_since(since)] == ["chart.png"]


# ------------------------------------------------ P1 步骤一：加固参数
def test_rootfs_is_read_only(shared: DockerContainer) -> None:
    """LLM 生成的代码不该能改镜像自带的任何东西。"""
    result = shared.exec("touch /etc/probe", timeout=10)

    assert result.exit_code != 0
    assert "denied" in result.output.lower() or "read-only" in result.output.lower()


def test_workspace_stays_writable_under_a_read_only_rootfs(shared: DockerContainer) -> None:
    """只读 rootfs 不能把 workspace 一起锁上，否则 agent 什么都产不出来。"""
    result = shared.exec("touch /workspace/probe && echo ok", timeout=10)

    assert result.output.strip() == "ok"


def test_tmp_is_writable_but_not_executable(shared: DockerContainer) -> None:
    """HOME 指向 /tmp，写配置必须可以；而 noexec 挡的是往家目录里落可执行文件。"""
    written = shared.exec("printf '#!/bin/sh\\necho ran\\n' > /tmp/x && chmod +x /tmp/x && echo ok", timeout=10)
    executed = shared.exec("/tmp/x", timeout=10)

    assert written.output.strip() == "ok"
    assert executed.exit_code != 0


def test_tmp_is_capped_at_the_configured_size(shared: DockerContainer) -> None:
    """Tmpfs 吃的是宿主机内存，不限容一句 dd 就能把宿主机写到 OOM。"""
    result = shared.exec("df -m /tmp | tail -1 | awk '{print $2}'", timeout=10)

    assert int(result.output.strip()) == 512


def test_the_sandbox_has_no_network(shared: DockerContainer) -> None:
    """零出网是 P1 定案的网络策略，也是不部署 devpi 的前提。"""
    result = shared.exec("python -c 'import socket; socket.create_connection((\"1.1.1.1\", 53), 2)'", timeout=20)

    assert result.exit_code != 0
    assert "unreachable" in result.output.lower() or "network" in result.output.lower()


def test_a_busy_loop_is_capped_to_one_cpu(workspace: Path) -> None:
    """死循环是常态而非攻击，它必须只烧掉自己那一份 CPU。"""
    with DockerContainer(thread_id="test-thread", workspace=workspace) as container:
        container.exec("nohup python -c 'while True: pass' >/dev/null 2>&1 &", timeout=10)
        time.sleep(4)
        usage = subprocess.run(
            ["docker", "stats", "--no-stream", "--format", "{{.CPUPerc}}", container.id],
            capture_output=True,
            text=True,
            check=True,
        )

    # docker stats 里 100% 就是一个核。留出余量是因为采样窗口本身有抖动
    assert float(usage.stdout.strip().rstrip("%")) < 150


def _host_process_count() -> int:
    listed = subprocess.run(["ps", "-e", "--no-headers"], capture_output=True, text=True, check=True)
    return len(listed.stdout.splitlines())


def test_a_fork_bomb_cannot_take_the_host_down(workspace: Path) -> None:
    """GVisor 下撞上 pids-limit 会直接掀掉整个沙箱，而不是让 fork 返回 EAGAIN。

    对平台是可接受的：沙箱池的健康探测会发现容器没了并重建，宿主机毫发无损。
    这条验的就是「没伤到宿主机」，不是「fork 优雅地失败了」。
    """
    before = _host_process_count()

    with DockerContainer(thread_id="test-thread", workspace=workspace) as container:
        # shlex.quote 而非 !r：repr 会把换行转义成字面的 \n 两个字符，
        # python -c 收到的就是一段语法错误的源码 —— 炸弹根本没点着，测试却照样绿
        result = container.exec(f"python -c {shlex.quote(FORK_BOMB)}", timeout=90)

    assert "SyntaxError" not in result.output
    assert _host_process_count() < before + 200


def test_runaway_output_is_truncated_with_a_visible_marker(workspace: Path) -> None:
    """一句 `while True: print(x)` 原样返回就能把网关吃爆，而 LLM 需要知道自己被截了。"""
    with DockerContainer(thread_id="test-thread", workspace=workspace) as container:
        result = container.exec("python -c 'while True: print(\"x\" * 1000)'", timeout=60)

    assert len(result.output.encode()) < OUTPUT_LIMIT_BYTE * 2
    assert TRUNCATION_MARKER in result.output


def test_normal_output_is_left_alone(shared: DockerContainer) -> None:
    result = shared.exec("echo 短输出", timeout=10)

    assert result.output == "短输出\n"
    assert TRUNCATION_MARKER not in result.output


def test_a_failing_command_keeps_its_exit_code_through_the_output_cap(shared: DockerContainer) -> None:
    """输出截断走的是管道，少了 pipefail 退出码会取自 head，失败会被报成成功。"""
    result = shared.exec("python -c 'import sys; sys.exit(7)'", timeout=20)

    assert result.exit_code == 7


def test_hardening_values_are_configurable_rather_than_baked_in(workspace: Path) -> None:
    """开发机与目标服务器的规格不同，限额必须是配置项。"""
    lean = Hardening(memory="256m", pids_limit=64, tmp_size="16m")

    with DockerContainer(thread_id="test-thread", workspace=workspace, hardening=lean) as container:
        result = container.exec("df -m /tmp | tail -1 | awk '{print $2}'", timeout=10)

    assert int(result.output.strip()) == 16


# ------------------------------------------------ P1 步骤三：broker 重启认领
def test_a_running_sandbox_is_discoverable_by_its_label(workspace: Path) -> None:
    """Broker 重启后靠 label 把容器认回来，没打上就成了谁也管不着的孤儿。"""
    thread_id = f"reclaim-probe-{os.getpid()}"

    with DockerContainer(thread_id=thread_id, workspace=workspace) as container:
        found = running_sandbox()

        assert found.get(thread_id) is not None
        assert container.id.startswith(found[thread_id])


def test_a_stopped_sandbox_is_no_longer_discoverable(workspace: Path) -> None:
    thread_id = f"reclaim-gone-{os.getpid()}"
    container = DockerContainer(thread_id=thread_id, workspace=workspace)
    container.start()

    container.stop()

    assert thread_id not in running_sandbox()


def test_an_adopted_container_is_usable_without_restarting_it(workspace: Path) -> None:
    """认领的意义：接着用同一个容器，而不是再起一个把旧的晾在那占内存。"""
    thread_id = f"reclaim-adopt-{os.getpid()}"
    original = DockerContainer(thread_id=thread_id, workspace=workspace)
    original.start()

    try:
        # 模拟 broker 重启：换一个全新的对象，只凭 docker ps 查到的 id 接管
        adopted = DockerContainer(thread_id=thread_id, workspace=workspace)
        adopted.adopt(running_sandbox()[thread_id])

        assert adopted.alive()
        assert adopted.exec("echo 接管成功", timeout=10).output.strip() == "接管成功"
    finally:
        original.stop()


def test_containers_outlive_the_process_that_started_them(workspace: Path) -> None:
    """--rm 是「退出时删」，不是「父进程没了就删」—— broker 崩溃不会带走沙箱。

    这一条是认领逻辑存在的前提，计划里点名要求确认而不是假设。
    """
    thread_id = f"reclaim-outlive-{os.getpid()}"
    started = subprocess.run(
        [
            sys.executable,
            "-c",
            f"import sys; sys.path.insert(0, {str(Path.cwd())!r});"
            "from pathlib import Path;"
            "from sandbox.container import DockerContainer;"
            f"c = DockerContainer(thread_id={thread_id!r}, workspace=Path({str(workspace)!r}));"
            "c.start(); print(c.id)",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    container_id = started.stdout.strip()

    try:
        # 起它的进程已经退出了，容器仍然在
        assert thread_id in running_sandbox()
    finally:
        subprocess.run(["docker", "rm", "-f", container_id], capture_output=True, check=False)
