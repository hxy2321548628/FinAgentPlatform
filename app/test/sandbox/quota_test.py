"""配额的测试。

派生与命令拼装是纯逻辑，这里全覆盖；「配额真的在 5GB 处触发 ENOSPC」需要 root
与真 XFS，在 deploy/test/hostile.sh 里验。
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from sandbox.quota import (
    PROJECT_ID_SPACE,
    NoQuota,
    QuotaError,
    XfsQuota,
    project_id,
)


# ------------------------------------------------------------------ projid 派生
def test_the_same_thread_always_gets_the_same_project_id() -> None:
    """容器销毁重建后要能设回同一份配额，派生不确定就等于每次换一个新 project。"""
    assert project_id("8f3a1b2c") == project_id("8f3a1b2c")


def test_different_threads_get_different_project_ids() -> None:
    assert project_id("thread-1") != project_id("thread-2")


def test_a_project_id_is_never_zero() -> None:
    """Projid 0 是「不属于任何 project」，落到它身上等于没设配额。"""
    assert all(project_id(f"thread-{index}") > 0 for index in range(2000))


def test_project_ids_stay_inside_the_usable_range() -> None:
    assert all(project_id(f"thread-{index}") <= PROJECT_ID_SPACE for index in range(2000))


def test_a_uuid_hex_thread_id_derives_cleanly() -> None:
    """真实的 thread_id 就是 uuid4().hex，派生要认得这个形状。"""
    assert project_id("75bddf025b3d42738f1f71497c010298") > 0


# ------------------------------------------------------------------ 命令拼装
class RecordingQuota(XfsQuota):
    """把要跑的命令记下来而不真的执行。"""

    def __init__(self, **argument: object) -> None:
        super().__init__(**argument)  # type: ignore[arg-type]
        self.ran: list[list[str]] = []

    def _run(self, subcommand: str) -> None:
        self.ran.append([*self._command, "-x", "-c", subcommand, str(self._mount_point)])


def test_assign_claims_the_directory_then_sets_the_limit(tmp_path: Path) -> None:
    """顺序反了的话，限额会先落在一个还没有目录的 project 上。"""
    quota = RecordingQuota(mount_point=tmp_path, limit="5g")

    quota.assign("thread-1", tmp_path / "thread-1")

    assert "project -s -p" in quota.ran[0][3]
    assert quota.ran[1][3] == f"limit -p bhard=5g {project_id('thread-1')}"


def test_assign_targets_the_mount_point(tmp_path: Path) -> None:
    quota = RecordingQuota(mount_point=tmp_path)

    quota.assign("thread-1", tmp_path / "thread-1")

    assert all(one[-1] == str(tmp_path) for one in quota.ran)


def test_the_command_prefix_is_configurable(tmp_path: Path) -> None:
    """Broker 容器内是 root 不必加 sudo，开发机上平台是普通用户则必须加。"""
    quota = RecordingQuota(mount_point=tmp_path, command=("sudo", "xfs_quota"))

    quota.assign("thread-1", tmp_path / "thread-1")

    assert quota.ran[0][:2] == ["sudo", "xfs_quota"]


def test_a_workspace_path_with_spaces_is_quoted(tmp_path: Path) -> None:
    """部署方给定的根目录可能带空格，不该把命令拆成两半。"""
    quota = RecordingQuota(mount_point=tmp_path)

    quota.assign("thread-1", Path("/data/my sandbox/thread-1"))

    assert "'/data/my sandbox/thread-1'" in quota.ran[0][3]


# ------------------------------------------------------------------ 失败不吞
def test_a_failing_quota_command_raises(tmp_path: Path) -> None:
    """设不上配额就等于这个 thread 能写满宿主机磁盘，不能只记个日志放过去。"""
    quota = XfsQuota(mount_point=tmp_path, command=("false",))

    with pytest.raises(QuotaError, match="设置配额失败"):
        quota.assign("thread-1", tmp_path / "thread-1")


def test_a_missing_quota_binary_raises(tmp_path: Path) -> None:
    quota = XfsQuota(mount_point=tmp_path, command=("zuel-no-such-binary",))

    with pytest.raises(QuotaError, match="调不起 xfs_quota"):
        quota.assign("thread-1", tmp_path / "thread-1")


# ------------------------------------------------------------------ 不设配额
def test_no_quota_does_nothing(tmp_path: Path) -> None:
    NoQuota().assign("thread-1", tmp_path)


# ------------------------------------------------------------------ 真 XFS
def _xfs_ready(path: Path) -> bool:
    if os.geteuid() != 0 or shutil.which("xfs_quota") is None or not path.is_dir():
        return False
    kind = subprocess.run(["findmnt", "-no", "FSTYPE", str(path)], capture_output=True, text=True, check=False)
    return kind.stdout.strip() == "xfs"


REPO_ROOT = Path(__file__).resolve().parents[3]
XFS_MOUNT = REPO_ROOT / "data" / "sandbox"


@pytest.mark.skipif(not _xfs_ready(XFS_MOUNT), reason="需要 root 且 data/sandbox 是 XFS（deploy/setup-xfs.sh）")
def test_a_real_quota_stops_writes_at_the_limit() -> None:
    """配额对目录生效，因此宿主侧直接写（文件工具走的正是这条路）同样被挡住。"""
    workspace = XFS_MOUNT / "quota-unit-probe"
    shutil.rmtree(workspace, ignore_errors=True)
    workspace.mkdir()
    try:
        XfsQuota(mount_point=XFS_MOUNT, limit="4m").assign("quota-unit-probe", workspace)

        with pytest.raises(OSError) as caught:
            (workspace / "fill").write_bytes(b"x" * (16 * 1024 * 1024))

        assert caught.value.errno == 28
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
