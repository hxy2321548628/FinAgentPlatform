"""配额的测试。

派生与命令拼装是纯逻辑，这里全覆盖。「配额真的触发 ENOSPC」那条也在这里，且
**走产品代码、以普通用户身份写**：deploy/test/hostile.sh 自己拼命令，验的是
「XFS 的机制成立」而不是「平台拼出来的命令对不对」，两者缺一不可。
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from app.sandbox.quota import (
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
    """把要跑的命令记下来而不真的执行。

    回读那一步要答一行「配额已生效」的报表，否则 assign 会正确地判成没设上。
    """

    def __init__(self, **argument: object) -> None:
        super().__init__(**argument)  # type: ignore[arg-type]
        self.ran: list[list[str]] = []

    def _run(self, subcommand: str) -> str:
        self.ran.append([*self._command, "-x", "-c", subcommand, str(self._mount_point)])
        if not subcommand.startswith("report"):
            return ""
        return f"#{subcommand.split()[-1]} 0 0 5242880 00 [--------]"

    def _claimed(self, workspace: Path) -> tuple[int, bool]:
        """认领成功：把刚才 `project -s` 报的那个 projid 原样答回去。

        子命令取倒数第二个元素而不是第 4 个 —— 命令前缀可能是 `sudo xfs_quota`
        两段，写死下标会在那条用例上错位。
        """
        return int(self.ran[0][-2].split()[-1]), True


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


def test_the_workspace_path_goes_in_without_shell_quoting(tmp_path: Path) -> None:
    """**`-c` 后面那串不经 shell**，xfs_quota 自己分词且不去引号。

    实测过一次：路径含非 ASCII（仓库在 `~/文档/` 下）时 `shlex.quote` 会加引号，
    xfs_quota 把引号当成路径的一部分，报 ENOENT 却退出 0 —— 于是这台机器上
    每个会话的目录都没被认领，配额从来没生效过，而没有任何地方报错。
    """
    quota = RecordingQuota(mount_point=tmp_path)
    workspace = Path("/data/文档/thread-1")

    quota.assign("thread-1", workspace)

    assert f"project -s -p {workspace} " in quota.ran[0][3]


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


# ------------------------------------------------------------------ 回读
class ReportingQuota(XfsQuota):
    """按给定的报表回答限额回读，认领结果由 `claimed` 给定。

    两面分开给：一面是 xfs_quota 嘴上说的（报表），一面是文件系统上的事实
    （inode 里的 projid）—— 实测这两面会不一致，而只信前者就会放过去。
    """

    def __init__(self, report: str, claimed: tuple[int, bool] = (0, False), **argument: object) -> None:
        super().__init__(**argument)  # type: ignore[arg-type]
        self._report = report
        self._claimed_value = claimed

    def _run(self, subcommand: str) -> str:
        return self._report if subcommand.startswith("report") else ""

    def _claimed(self, workspace: Path) -> tuple[int, bool]:
        return self._claimed_value


def test_a_workspace_that_never_got_claimed_raises(tmp_path: Path) -> None:
    """**`limit` 是设在 projid 上的，目录没认领它照样成功。**

    只回读限额会得到「有上限但没人受它约束」的假绿。两条真实路径都长这样：
    带空格的路径被 xfs_quota 在空格处截断；容器里没有块设备节点时三条命令
    全部只往 stderr 打一句然后退出 0。
    """
    identifier = project_id("thread-1")
    quota = ReportingQuota(
        f"#{identifier} 0 0 5242880 00 [--------]",
        claimed=(0, False),
        mount_point=tmp_path,
    )

    with pytest.raises(QuotaError, match="没有被认领"):
        quota.assign("thread-1", Path("/data/my sandbox/thread-1"))


def test_a_workspace_claimed_by_another_project_raises(tmp_path: Path) -> None:
    """认领上了但归错 project，等于受的是别人那份配额的约束。"""
    identifier = project_id("thread-1")
    quota = ReportingQuota(
        f"#{identifier} 0 0 5242880 00 [--------]",
        claimed=(identifier + 1, True),
        mount_point=tmp_path,
    )

    with pytest.raises(QuotaError, match="没有被认领"):
        quota.assign("thread-1", tmp_path / "thread-1")


def test_a_workspace_without_the_inheritance_flag_raises(tmp_path: Path) -> None:
    """继承标志没设的话，目录本身归了 project，而它里面新建的文件不归。"""
    identifier = project_id("thread-1")
    quota = ReportingQuota(
        f"#{identifier} 0 0 5242880 00 [--------]",
        claimed=(identifier, False),
        mount_point=tmp_path,
    )

    with pytest.raises(QuotaError, match="没有被认领"):
        quota.assign("thread-1", tmp_path / "thread-1")


def test_a_quota_command_that_exits_zero_without_setting_anything_raises(tmp_path: Path) -> None:
    """**退出码会骗人**：xfs_quota 探不到挂载点时把错误打到 stderr 却退出 0。

    实测过一次：workspace 所在的 loop 挂载重启后没挂回来，此后每个会话的 5GB
    上限一个都没设上，而 check=True 一次都没触发、日志里一条记录都没有。
    """
    quota = XfsQuota(mount_point=tmp_path, command=("true",))

    with pytest.raises(QuotaError, match="配额没有生效"):
        quota.assign("thread-1", tmp_path / "thread-1")


def test_a_project_reported_with_a_zero_hard_limit_raises(tmp_path: Path) -> None:
    """硬上限 0 就是「没有上限」，这个 project 照样能写满宿主机磁盘。"""
    identifier = project_id("thread-1")
    quota = ReportingQuota(f"#{identifier} 0 0 0 00 [--------]", claimed=(identifier, True), mount_point=tmp_path)

    with pytest.raises(QuotaError, match="配额没有生效"):
        quota.assign("thread-1", tmp_path / "thread-1")


def test_a_report_about_some_other_project_raises(tmp_path: Path) -> None:
    """认的必须是本会话那个 projid —— 别人身上有配额不等于这一个有。"""
    quota = ReportingQuota(
        "#999999 0 0 5242880 00 [--------]", claimed=(project_id("thread-1"), True), mount_point=tmp_path
    )

    with pytest.raises(QuotaError, match="配额没有生效"):
        quota.assign("thread-1", tmp_path / "thread-1")


def test_a_project_reported_with_a_real_hard_limit_passes(tmp_path: Path) -> None:
    identifier = project_id("thread-1")
    quota = ReportingQuota(f"#{identifier} 0 0 5242880 00 [--------]", claimed=(identifier, True), mount_point=tmp_path)

    quota.assign("thread-1", tmp_path / "thread-1")


def test_the_read_back_asks_only_about_this_project(tmp_path: Path) -> None:
    """按 projid 上下界问，回来就只有一行，不必在整份报表里找。"""
    identifier = project_id("thread-1")
    quota = RecordingQuota(mount_point=tmp_path)

    quota.assign("thread-1", tmp_path / "thread-1")

    assert quota.ran[2][3] == f"report -p -N -b -n -L {identifier} -U {identifier}"


# ------------------------------------------------------------------ 不设配额
def test_no_quota_does_nothing(tmp_path: Path) -> None:
    NoQuota().assign("thread-1", tmp_path)


# ------------------------------------------------------------------ 真 XFS
REPO_ROOT = Path(__file__).resolve().parents[3]
XFS_MOUNT = REPO_ROOT / "data" / "sandbox"

# 以 root 跑就直接调，普通用户走 setup-xfs.sh 放行的免密 sudo。
# `-n` 是必须的：口令提示会让整个套件挂在那儿等输入
QUOTA_COMMAND = ("xfs_quota",) if os.geteuid() == 0 else ("sudo", "-n", "xfs_quota")


def _quota_ready(mount: Path) -> bool:
    """挂载是 XFS + prjquota、挂载点可写、且 xfs_quota 免密调得起来。

    **刻意不要求 root**：root 那一程验不到东西 —— 原来的版本要求 root，于是它从来
    没在 `make all` 里跑过，而配额没生效整整两天没人发现。
    """
    if shutil.which("xfs_quota") is None or not mount.is_dir() or not os.access(mount, os.W_OK):
        return False
    mounted = subprocess.run(
        ["findmnt", "-no", "FSTYPE,OPTIONS", str(mount)], capture_output=True, text=True, check=False
    )
    if not mounted.stdout.startswith("xfs") or "prjquota" not in mounted.stdout:
        return False
    state = subprocess.run(
        [*QUOTA_COMMAND, "-x", "-c", "state -p", str(mount)], capture_output=True, text=True, check=False
    )
    return state.returncode == 0 and "Enforcement: ON" in state.stdout


@pytest.mark.skipif(
    not _quota_ready(XFS_MOUNT),
    reason="需要 data/sandbox 是 XFS + prjquota、挂载点可写、xfs_quota 免密可调（deploy/setup-xfs.sh）",
)
def test_a_real_quota_stops_writes_at_the_limit() -> None:
    """配额对目录生效，因此宿主侧直接写（文件工具走的正是这条路）同样被挡住。

    **必须走产品代码，不能自己拼命令**：`hostile.sh` ③ 自己拼，于是它验的是
    「XFS 的机制成立」而不是「平台拼出来的命令对不对」—— 实测漏掉了一个把路径
    加引号、让认领全数失败的 bug，而那条破坏性测试照样是绿的。
    """
    workspace = XFS_MOUNT / "quota-unit-probe"
    shutil.rmtree(workspace, ignore_errors=True)
    workspace.mkdir()
    try:
        XfsQuota(mount_point=XFS_MOUNT, limit="4m", command=QUOTA_COMMAND).assign("quota-unit-probe", workspace)

        with pytest.raises(OSError) as caught:
            (workspace / "fill").write_bytes(b"x" * (16 * 1024 * 1024))

        assert caught.value.errno == 28
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
