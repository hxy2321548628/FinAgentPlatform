from pathlib import Path

import pytest

from sandbox.path import OUTPUT_DIR, PathEscapeError
from sandbox.workspace import Workspace


@pytest.fixture
def space(tmp_path: Path) -> Workspace:
    return Workspace(root=tmp_path)


# ------------------------------------------------------------------ 会话
def test_a_new_thread_gets_a_directory(space: Workspace, tmp_path: Path) -> None:
    thread_id = space.create()

    assert (tmp_path / thread_id).is_dir()


def test_each_thread_gets_a_distinct_id(space: Workspace) -> None:
    assert space.create() != space.create()


def test_a_created_thread_exists(space: Workspace) -> None:
    assert space.exists(space.create())


def test_an_unknown_thread_does_not_exist(space: Workspace) -> None:
    assert not space.exists("never-created")


@pytest.mark.parametrize("thread_id", ["../elsewhere", "a/b", "", "."])
def test_an_illegal_thread_id_reads_as_not_existing(space: Workspace, thread_id: str) -> None:
    """分成「不存在」和「格式不对」两种回答，等于告诉调用方哪些 id 是真的。"""
    assert not space.exists(thread_id)


def test_path_creates_the_directory_on_demand(space: Workspace, tmp_path: Path) -> None:
    workspace = space.path("thread-1")

    assert workspace == tmp_path / "thread-1"
    assert workspace.is_dir()


def test_path_rejects_a_thread_id_that_escapes_the_root(space: Workspace) -> None:
    with pytest.raises(PathEscapeError):
        space.path("../elsewhere")


# ------------------------------------------------------------------ 上传
def test_an_uploaded_file_lands_in_the_thread_directory(space: Workspace, tmp_path: Path) -> None:
    thread_id = space.create()

    saved = space.save(thread_id, "holdings.csv", b"a,b\n")

    assert saved == tmp_path / thread_id / "holdings.csv"
    assert saved.read_bytes() == b"a,b\n"


def test_the_agent_sees_an_uploaded_file_at_the_workspace_root(space: Workspace) -> None:
    """提示词告诉 agent 工作目录是 /workspace，上传的数据必须就在那一层。"""
    thread_id = space.create()

    saved = space.save(thread_id, "holdings.csv", b"x")

    assert saved.parent == space.path(thread_id)


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("../../etc/passwd", "passwd"),
        ("/etc/passwd", "passwd"),
        ("sub/dir/data.csv", "data.csv"),
    ],
)
def test_a_traversing_filename_is_reduced_to_its_last_segment(
    space: Workspace, tmp_path: Path, filename: str, expected: str
) -> None:
    """文件名来自 HTTP 请求，是不可信输入。"""
    thread_id = space.create()

    saved = space.save(thread_id, filename, b"x")

    assert saved == tmp_path / thread_id / expected


@pytest.mark.parametrize("filename", ["", "..", ".", "/", "../"])
def test_a_filename_with_no_usable_segment_is_rejected(space: Workspace, filename: str) -> None:
    thread_id = space.create()

    with pytest.raises(PathEscapeError):
        space.save(thread_id, filename, b"x")


def test_uploading_the_same_name_twice_overwrites(space: Workspace) -> None:
    thread_id = space.create()
    space.save(thread_id, "data.csv", b"old")

    saved = space.save(thread_id, "data.csv", b"new")

    assert saved.read_bytes() == b"new"


# ------------------------------------------------------------------ 产物
def test_an_artifact_resolves_under_the_output_directory(space: Workspace) -> None:
    thread_id = space.create()
    output_dir = space.path(thread_id) / OUTPUT_DIR
    output_dir.mkdir()
    (output_dir / "chart.png").write_bytes(b"png")

    assert space.artifact(thread_id, "chart.png").read_bytes() == b"png"


def test_a_nested_artifact_resolves(space: Workspace) -> None:
    thread_id = space.create()
    nested = space.path(thread_id) / OUTPUT_DIR / "figure"
    nested.mkdir(parents=True)
    (nested / "chart.png").write_bytes(b"png")

    assert space.artifact(thread_id, "figure/chart.png").read_bytes() == b"png"


def test_a_missing_artifact_resolves_but_does_not_exist(space: Workspace) -> None:
    """路径合法与文件存在是两回事，前者归本模块，后者归调用方决定回什么状态码。"""
    thread_id = space.create()

    assert not space.artifact(thread_id, "never-made.png").exists()


@pytest.mark.parametrize("relative", ["../holdings.csv", "../../etc/passwd", "/etc/passwd"])
def test_an_artifact_path_that_escapes_the_output_directory_is_rejected(space: Workspace, relative: str) -> None:
    """不挡住的话，产物下载就成了任意文件读取。"""
    thread_id = space.create()

    with pytest.raises(PathEscapeError):
        space.artifact(thread_id, relative)


def test_an_artifact_symlink_pointing_outside_is_rejected(space: Workspace, tmp_path: Path) -> None:
    """Agent 能在沙箱里创建符号链接，纯字符串校验拦不住这一条。"""
    thread_id = space.create()
    output_dir = space.path(thread_id) / OUTPUT_DIR
    output_dir.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("凭据", encoding="utf-8")
    (output_dir / "link.txt").symlink_to(secret)

    with pytest.raises(PathEscapeError):
        space.artifact(thread_id, "link.txt")
