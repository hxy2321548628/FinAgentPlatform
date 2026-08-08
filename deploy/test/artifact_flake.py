"""产物判定的复现脚本：基准与判据用不同时钟时，产物会被静默漏掉。

**这不是单测，是复现脚本。** 它复现的是一条概率约 2.6% 的偶发红：跑一次看不出问题，
跑几百次才有一次红，而红的时候没有任何报错指向原因 —— 产物列表就是空的。

机制：判据读的是 inode 时间戳，那是内核的**粗粒度时钟**（每个 tick 更新一次，NOHZ 下
进程一空闲就停在上一次 tick 上）；`time.time_ns()` 读的是细粒度时钟。两者最多差一个
tick，实测约 0.4 毫秒。拿墙钟当基准，紧接着写下的产物 mtime 反而更早。

两种基准各跑一轮，同一条判据：

    cd app && PYTHONPATH=. uv run python ../deploy/test/artifact_flake.py [轮次]

墙钟基准必须红（漏掉 > 0），文件系统基准必须全绿（漏掉 == 0）。
**「墙钟那一轮也全绿」同样算失败** —— 那说明这次没造出要测的场景，判据没被证伪过。
"""

import statistics
import sys
import time
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from sandbox.backend import SandboxBackend
from sandbox.container import CommandResult
from sandbox.path import OUTPUT_DIR

DEFAULT_ROUNDS = 1000

# 取基准之前的空档。真实路径里这是 broker 那次 HTTP 往返的量级，也正是偏差张开的地方 ——
# 进程一空闲，内核的粗粒度时钟就不再被推进
IDLE_SECOND = 0.02

# 墙钟那一轮至少要漏掉这么多次才算复现成功。低于它说明场景没造出来
MINIMUM_MISS = 1

# 基准的取法：给 backend 与它的 workspace，还回一个纳秒时间戳
type Mark = Callable[[SandboxBackend, Path], int]


class NoContainer:
    """产物判定不进容器，这里只是把构造参数填上。"""

    @property
    def id(self) -> str:
        return "no-container"

    def exec(self, command: str, *, timeout: int) -> CommandResult:
        """Raises: NotImplementedError: 复现脚本从不执行命令。"""
        raise NotImplementedError


def wall_mark(backend: SandboxBackend, workspace: Path) -> int:
    """修复前的基准：读本进程的墙钟。"""
    (workspace / OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    return time.time_ns()


def filesystem_mark(backend: SandboxBackend, workspace: Path) -> int:
    """修复后的基准：向文件系统要。"""
    return backend.artifact_mark()


def run_rounds(root: Path, rounds: int, mark: Mark) -> tuple[int, list[int]]:
    """跑若干轮「取基准 → 写产物 → 认领」，返回漏掉的次数与每轮的时间差。"""
    missed = 0
    delta: list[int] = []
    for _ in range(rounds):
        workspace = root / uuid4().hex
        workspace.mkdir()
        # **目录要自己建。** 取基准那一步刻意不建它 —— 那句 mkdir 跑在 broker 进程里，
        # 而 broker 在容器里是 root，建出来的目录以宿主用户跑的沙箱写不进去。
        # 真实里这个目录由沙箱建，这里就是在替沙箱做那件事
        (workspace / OUTPUT_DIR).mkdir()
        backend = SandboxBackend(workspace=workspace, container=NoContainer())
        time.sleep(IDLE_SECOND)
        since = mark(backend, workspace)
        chart = workspace / OUTPUT_DIR / "chart.png"
        chart.write_bytes(b"png")
        delta.append(chart.stat().st_mtime_ns - since)
        if backend.artifact_since(since) != [chart]:
            missed += 1
    return missed, delta


def report(label: str, missed: int, rounds: int, delta: list[int]) -> None:
    """打一行结果，带上时间差的分布 —— 只报「漏没漏」看不出离边界还有多远。"""
    print(
        f"  {label}：漏掉 {missed}/{rounds}（{missed / rounds:.2%}）"
        f"  最负 {min(delta)} ns  中位 {int(statistics.median(delta))} ns"
    )


def main(rounds: int) -> int:
    """两种基准各跑一轮，返回进程退出码。"""
    print(f"产物判定复现：两种基准各 {rounds} 轮")
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        wall_missed, wall_delta = run_rounds(root, rounds, wall_mark)
        report("墙钟基准（修复前）    ", wall_missed, rounds, wall_delta)
        filesystem_missed, filesystem_delta = run_rounds(root, rounds, filesystem_mark)
        report("文件系统基准（修复后）", filesystem_missed, rounds, filesystem_delta)

    if wall_missed < MINIMUM_MISS:
        print(f"❌ 墙钟基准一次都没漏 —— 这次没造出要测的场景，判据没被证伪过（需 ≥ {MINIMUM_MISS}）")
        return 1
    if filesystem_missed:
        print(f"❌ 文件系统基准漏掉 {filesystem_missed} 次，修复不成立")
        return 1
    print("✅ 墙钟基准会漏、文件系统基准不漏 —— 复现成立且修复有效")
    return 0


if __name__ == "__main__":
    sys.exit(main(int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_ROUNDS))
