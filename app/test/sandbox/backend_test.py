import time
from pathlib import Path

import pytest

from sandbox.backend import OUTPUT_DIR, SandboxBackend
from sandbox.container import CommandResult, ContainerError

WORKSPACE_FILE = "/workspace/data.csv"


class FakeContainer:
    """记录调用的假容器，让文件方法的测试不必起 Docker。"""

    def __init__(self, output: str = "", exit_code: int = 0, failure: Exception | None = None) -> None:
        self._output = output
        self._exit_code = exit_code
        self._failure = failure
        self.command: list[tuple[str, int]] = []

    @property
    def id(self) -> str:
        return "fake-container-id"

    def exec(self, command: str, *, timeout: int) -> CommandResult:
        self.command.append((command, timeout))
        if self._failure is not None:
            raise self._failure
        return CommandResult(output=self._output, exit_code=self._exit_code)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    space = tmp_path / "sandbox" / "thread-1"
    space.mkdir(parents=True)
    return space


@pytest.fixture
def container() -> FakeContainer:
    return FakeContainer()


@pytest.fixture
def backend(workspace: Path, container: FakeContainer) -> SandboxBackend:
    return SandboxBackend(workspace=workspace, container=container)


# ---------------------------------------------------------------- 七个文件工具
def test_write_then_read_round_trips(backend: SandboxBackend) -> None:
    written = backend.write(WORKSPACE_FILE, "a,b\n1,2\n")

    assert written.error is None
    result = backend.read(WORKSPACE_FILE)
    assert result.error is None
    assert result.file_data is not None
    assert result.file_data["content"] == "a,b\n1,2\n"


def test_write_lands_in_the_host_workspace(backend: SandboxBackend, workspace: Path) -> None:
    """写进去的文件必须真落在 bind-mount 目录里，否则容器里的代码读不到。"""
    backend.write("/workspace/hello.py", "print('hello')")

    assert (workspace / "hello.py").read_text(encoding="utf-8") == "print('hello')"


def test_ls_lists_workspace_entries(backend: SandboxBackend, workspace: Path) -> None:
    (workspace / "data.csv").write_text("x", encoding="utf-8")

    result = backend.ls("/workspace")

    assert result.error is None
    assert result.entries is not None
    assert [entry["path"] for entry in result.entries] == ["/data.csv"]


def test_edit_replaces_the_string(backend: SandboxBackend) -> None:
    backend.write("/workspace/a.py", "value = 1")

    result = backend.edit("/workspace/a.py", "1", "2")

    assert result.error is None
    assert result.occurrences == 1


def test_delete_removes_the_file(backend: SandboxBackend, workspace: Path) -> None:
    backend.write("/workspace/tmp.txt", "x")

    result = backend.delete("/workspace/tmp.txt")

    assert result.error is None
    assert not (workspace / "tmp.txt").exists()


def test_glob_matches_by_pattern(backend: SandboxBackend) -> None:
    backend.write("/workspace/a.py", "x")
    backend.write("/workspace/b.csv", "x")

    result = backend.glob("*.py")

    assert result.error is None
    assert result.matches is not None
    assert [match["path"] for match in result.matches] == ["/a.py"]


def test_grep_finds_the_literal(backend: SandboxBackend) -> None:
    backend.write("/workspace/a.py", "import pandas\nprint(1)\n")

    result = backend.grep("pandas")

    assert result.error is None
    assert result.matches is not None
    assert result.matches[0]["line"] == 1


def test_upload_then_download_round_trips(backend: SandboxBackend) -> None:
    uploaded = backend.upload_files([("/workspace/in.csv", b"a,b\n")])

    assert [item.error for item in uploaded] == [None]
    downloaded = backend.download_files(["/workspace/in.csv"])
    assert downloaded[0].content == b"a,b\n"


# -------------------------------------------------- 路径越界一律返回 error，不抛
def test_parent_traversal_returns_error_instead_of_raising(backend: SandboxBackend) -> None:
    result = backend.read("/workspace/../../etc/passwd")

    assert result.error is not None


def test_traversal_write_does_not_touch_the_host(backend: SandboxBackend, workspace: Path) -> None:
    result = backend.write("/workspace/../escaped.txt", "x")

    assert result.error is not None
    assert not (workspace.parent / "escaped.txt").exists()


def test_symlink_escape_returns_error_instead_of_raising(
    backend: SandboxBackend, tmp_path: Path, workspace: Path
) -> None:
    """符号链接是绕过前缀检查的常规手法，必须在解析后被拦下。"""
    secret = tmp_path / "secret.txt"
    secret.write_text("凭据", encoding="utf-8")
    (workspace / "link.txt").symlink_to(secret)

    result = backend.read("/workspace/link.txt")

    assert result.error is not None


def test_path_outside_the_sandbox_root_returns_error(backend: SandboxBackend) -> None:
    result = backend.read("/etc/passwd")

    assert result.error is not None


def test_every_file_method_rejects_escape_without_raising(backend: SandboxBackend) -> None:
    """穿越路径不能让任何一个工具抛异常 —— 抛出会让整个 run 失败。"""
    escape = "/etc/passwd"

    assert backend.read(escape).error is not None
    assert backend.write(escape, "x").error is not None
    assert backend.edit(escape, "a", "b").error is not None
    assert backend.delete(escape).error is not None
    assert backend.ls(escape).error is not None
    assert backend.glob("*.csv", escape).error is not None
    assert backend.grep("x", escape).error is not None
    assert backend.upload_files([(escape, b"x")])[0].error is not None
    assert backend.download_files([escape])[0].error is not None


# ------------------------------------------------------ 工具自身的失败也要返回
def test_reading_a_missing_file_returns_error(backend: SandboxBackend) -> None:
    result = backend.read("/workspace/nope.csv")

    assert result.error is not None


def test_edit_with_absent_string_returns_error(backend: SandboxBackend) -> None:
    backend.write("/workspace/a.py", "value = 1")

    result = backend.edit("/workspace/a.py", "不存在的串", "x")

    assert result.error is not None


def test_delete_missing_file_returns_error(backend: SandboxBackend) -> None:
    result = backend.delete("/workspace/nope.txt")

    assert result.error is not None


# ------------------------------------------------------------------- execute
def test_execute_delegates_to_the_container(workspace: Path) -> None:
    container = FakeContainer(output="hello\n", exit_code=0)
    backend = SandboxBackend(workspace=workspace, container=container)

    response = backend.execute("python hello.py")

    assert response.output == "hello\n"
    assert response.exit_code == 0
    assert container.command[0][0] == "python hello.py"


def test_execute_passes_the_timeout_through(workspace: Path) -> None:
    container = FakeContainer()
    backend = SandboxBackend(workspace=workspace, container=container)

    backend.execute("sleep 1", timeout=5)

    assert container.command[0][1] == 5


def test_execute_failure_returns_error_output_instead_of_raising(workspace: Path) -> None:
    """容器起不来、超时、docker 不可达 —— 都得让 LLM 看到错误，而不是让 run 挂掉。"""
    container = FakeContainer(failure=ContainerError("容器已停止"))
    backend = SandboxBackend(workspace=workspace, container=container)

    response = backend.execute("python hello.py")

    assert "容器已停止" in response.output
    assert response.exit_code != 0


def test_id_is_the_container_id(backend: SandboxBackend) -> None:
    assert backend.id == "fake-container-id"


# -------------------------------------------------------------------- 产物判定
def test_artifact_lists_files_written_under_outputs(backend: SandboxBackend, workspace: Path) -> None:
    since = time.time()
    output_dir = workspace / OUTPUT_DIR
    output_dir.mkdir()
    (output_dir / "chart.png").write_bytes(b"png")

    assert backend.artifact_since(since) == [output_dir / "chart.png"]


def test_artifact_ignores_files_outside_outputs(backend: SandboxBackend, workspace: Path) -> None:
    """只认 outputs/，否则中间文件与输入 CSV 都会被当成产物。"""
    since = time.time()
    (workspace / "scratch.pkl").write_bytes(b"x")

    assert backend.artifact_since(since) == []


def test_artifact_ignores_files_untouched_by_this_run(backend: SandboxBackend, workspace: Path) -> None:
    output_dir = workspace / OUTPUT_DIR
    output_dir.mkdir()
    old = output_dir / "previous.png"
    old.write_bytes(b"png")

    assert backend.artifact_since(time.time() + 1) == []


def test_artifact_is_empty_when_outputs_never_created(backend: SandboxBackend) -> None:
    assert backend.artifact_since(time.time()) == []


def test_artifact_ignores_symlinks(backend: SandboxBackend, workspace: Path, tmp_path: Path) -> None:
    """产物会被下载给教师，跟随符号链接等于把任意宿主文件当产物送出去。"""
    secret = tmp_path / "secret.txt"
    secret.write_text("凭据", encoding="utf-8")
    output_dir = workspace / OUTPUT_DIR
    output_dir.mkdir()

    since = time.time()
    (output_dir / "chart.png").symlink_to(secret)

    assert backend.artifact_since(since) == []


# ------------------------------------------------------------- 异步入口同源
async def test_aread_reaches_the_same_file(backend: SandboxBackend) -> None:
    backend.write(WORKSPACE_FILE, "a,b\n")

    result = await backend.aread(WORKSPACE_FILE)

    assert result.error is None
    assert result.file_data is not None
    assert result.file_data["content"] == "a,b\n"


async def test_aexecute_reaches_the_container(workspace: Path) -> None:
    container = FakeContainer(output="done\n")
    backend = SandboxBackend(workspace=workspace, container=container)

    response = await backend.aexecute("python x.py")

    assert response.output == "done\n"
    assert container.command[0][0] == "python x.py"


async def test_awrite_escape_returns_error_instead_of_raising(backend: SandboxBackend) -> None:
    result = await backend.awrite("/etc/passwd", "x")

    assert result.error is not None
