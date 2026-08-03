from pathlib import Path

import pytest

from sandbox.path import SANDBOX_ROOT, PathEscapeError, thread_workspace, to_virtual_path

THREAD_ID = "8f3a2b1c"


def test_sandbox_root_maps_to_the_virtual_root() -> None:
    assert to_virtual_path(SANDBOX_ROOT) == "/"


def test_trailing_slash_maps_to_the_virtual_root() -> None:
    assert to_virtual_path(f"{SANDBOX_ROOT}/") == "/"


def test_file_under_root_drops_the_prefix() -> None:
    assert to_virtual_path(f"{SANDBOX_ROOT}/data.csv") == "/data.csv"


def test_nested_path_drops_the_prefix() -> None:
    assert to_virtual_path(f"{SANDBOX_ROOT}/outputs/chart.png") == "/outputs/chart.png"


def test_traversal_is_forwarded_for_the_filesystem_layer_to_reject() -> None:
    """`..` 不在这里拦。

    符号链接要在真实文件系统上解析才能判定越界，纯字符串处理挡不住，
    因此统一交给 FilesystemBackend 的规范化去拒绝，避免两层各挡一半。
    """
    assert to_virtual_path(f"{SANDBOX_ROOT}/../etc/passwd") == "/../etc/passwd"


def test_path_outside_sandbox_root_is_rejected() -> None:
    with pytest.raises(PathEscapeError):
        to_virtual_path("/etc/passwd")


def test_prefix_lookalike_is_rejected() -> None:
    """`/workspaceevil` 不是 `/workspace` 的子路径，光靠去前缀会把它放进来。"""
    with pytest.raises(PathEscapeError):
        to_virtual_path(f"{SANDBOX_ROOT}evil/data.csv")


def test_relative_path_is_rejected() -> None:
    """协议要求路径以 / 开头；相对路径的基准目录不确定，不猜。"""
    with pytest.raises(PathEscapeError):
        to_virtual_path("data.csv")


def test_empty_path_is_rejected() -> None:
    with pytest.raises(PathEscapeError):
        to_virtual_path("")


def test_thread_workspace_is_a_child_of_the_root(tmp_path: Path) -> None:
    assert thread_workspace(tmp_path, THREAD_ID) == tmp_path / THREAD_ID


def test_thread_id_escaping_the_root_is_rejected(tmp_path: Path) -> None:
    """thread_id 从 HTTP 路径参数来，同样是外部输入。"""
    with pytest.raises(PathEscapeError):
        thread_workspace(tmp_path, "../other")


def test_thread_id_with_separator_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(PathEscapeError):
        thread_workspace(tmp_path, "a/b")


def test_empty_thread_id_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(PathEscapeError):
        thread_workspace(tmp_path, "")
