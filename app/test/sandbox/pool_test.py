"""沙箱池的测试，全部用假容器 —— 这里验的是调度，不是 Docker。

真 Docker 的部分在 container_test.py。
"""

import asyncio
from pathlib import Path

import pytest

from sandbox.container import CommandResult, ContainerError
from sandbox.pool import SandboxPool, SandboxQueueTimeoutError
from sandbox.workspace import Workspace


class FakeContainer:
    """记录自己被起停过几次的假容器。"""

    def __init__(self, thread_id: str, workspace: Path, image: str = "fake") -> None:
        self.thread_id = thread_id
        self.workspace = workspace
        self.image = image
        self.start_count = 0
        self.stopped = False
        self.broken = False
        self.adopted: str | None = None
        self.start_error: str | None = None

    @property
    def id(self) -> str:
        return f"fake-{self.workspace.name}"

    def start(self) -> None:
        if self.start_error is not None:
            raise ContainerError(self.start_error)
        self.start_count += 1
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True

    def alive(self) -> bool:
        return not self.stopped and not self.broken

    def adopt(self, container_id: str) -> None:
        self.adopted = container_id

    def exec(self, command: str, *, timeout: int) -> CommandResult:
        return CommandResult(output=command, exit_code=0)


class Factory:
    """按 workspace 造假容器，并留住每一个供断言。"""

    def __init__(self) -> None:
        self.made: list[FakeContainer] = []

    def __call__(self, thread_id: str, workspace: Path) -> FakeContainer:
        container = FakeContainer(thread_id, workspace)
        self.made.append(container)
        return container


class FakeClock:
    """手动推进的单调时钟。

    回收判据全是时间差，用真实时钟测只能靠 sleep 逼近 —— 而 sleep 在满负载的
    测试里会被调度器拖长，表现为偶发的红。偶发的红比没有测试更糟。
    """

    def __init__(self) -> None:
        self.reading = 0.0

    def __call__(self) -> float:
        return self.reading

    def advance(self, second: float) -> None:
        self.reading += second


@pytest.fixture
def factory() -> Factory:
    return Factory()


def make_pool(tmp_path: Path, factory: Factory, **override: object) -> SandboxPool:
    argument: dict[str, object] = {
        "workspace": Workspace(root=tmp_path),
        "max_container": 2,
        "idle_timeout": 1800.0,
        "queue_timeout": 1.0,
        "container_factory": factory,
    }
    argument.update(override)
    return SandboxPool(**argument)  # type: ignore[arg-type]


# ------------------------------------------------------------------ 复用
async def test_acquire_starts_a_container_for_a_new_thread(tmp_path: Path, factory: Factory) -> None:
    pool = make_pool(tmp_path, factory)

    container = await pool.acquire("thread-1")

    assert container.id == "fake-thread-1"
    assert factory.made[0].start_count == 1
    await pool.aclose()


async def test_the_same_thread_reuses_its_container(tmp_path: Path, factory: Factory) -> None:
    """per-thread 长驻的全部意义：装过的包、写过的文件在后续调用里还在。"""
    pool = make_pool(tmp_path, factory)

    first = await pool.acquire("thread-1")
    await pool.release("thread-1")
    second = await pool.acquire("thread-1")

    assert first is second
    assert len(factory.made) == 1
    await pool.aclose()


async def test_concurrent_runs_of_one_thread_share_one_container(tmp_path: Path, factory: Factory) -> None:
    pool = make_pool(tmp_path, factory)

    await pool.acquire("thread-1")
    await pool.acquire("thread-1")

    assert len(factory.made) == 1
    await pool.aclose()


async def test_each_thread_gets_its_own_workspace(tmp_path: Path, factory: Factory) -> None:
    """两个课题的工作目录必须互不可见。"""
    pool = make_pool(tmp_path, factory)

    await pool.acquire("thread-1")
    await pool.acquire("thread-2")

    assert {one.workspace for one in factory.made} == {tmp_path / "thread-1", tmp_path / "thread-2"}
    await pool.aclose()


async def test_a_thread_id_that_escapes_the_workspace_root_is_rejected(tmp_path: Path, factory: Factory) -> None:
    """thread_id 参与拼路径，越界的值不能落到 workspace 根之外。"""
    pool = make_pool(tmp_path, factory)

    with pytest.raises(ValueError, match="thread_id"):
        await pool.acquire("../elsewhere")
    await pool.aclose()


# ------------------------------------------------------------------ 上限与 LRU
async def test_an_idle_container_is_evicted_to_make_room(tmp_path: Path, factory: Factory) -> None:
    pool = make_pool(tmp_path, factory, max_container=1)

    await pool.acquire("thread-1")
    await pool.release("thread-1")
    await pool.acquire("thread-2")

    assert factory.made[0].stopped
    assert len(factory.made) == 2
    await pool.aclose()


async def test_eviction_picks_the_least_recently_used(tmp_path: Path, factory: Factory) -> None:
    pool = make_pool(tmp_path, factory, max_container=2)

    await pool.acquire("thread-1")
    await pool.release("thread-1")
    await pool.acquire("thread-2")
    await pool.release("thread-2")
    # thread-1 重新被用过，于是 thread-2 成了最久未用的那个
    await pool.acquire("thread-1")
    await pool.release("thread-1")

    await pool.acquire("thread-3")

    by_thread = {one.workspace.name: one for one in factory.made}
    assert by_thread["thread-2"].stopped
    assert not by_thread["thread-1"].stopped
    await pool.aclose()


async def test_a_busy_container_is_never_evicted(tmp_path: Path, factory: Factory) -> None:
    """正在跑的 run 被抽走容器，等于凭空失败一次。"""
    pool = make_pool(tmp_path, factory, max_container=1, queue_timeout=0.05)

    await pool.acquire("thread-1")

    with pytest.raises(SandboxQueueTimeoutError):
        await pool.acquire("thread-2")
    assert not factory.made[0].stopped
    await pool.aclose()


# ------------------------------------------------------------------ 排队
async def test_a_queued_request_is_served_once_a_slot_frees_up(tmp_path: Path, factory: Factory) -> None:
    pool = make_pool(tmp_path, factory, max_container=1, queue_timeout=5.0)
    await pool.acquire("thread-1")

    waiting = asyncio.create_task(pool.acquire("thread-2"))
    await asyncio.sleep(0)
    await pool.release("thread-1")
    container = await waiting

    assert container.id == "fake-thread-2"
    await pool.aclose()


async def test_the_queue_is_served_first_in_first_out(tmp_path: Path, factory: Factory) -> None:
    """FIFO 之外的顺序会让先来的教师被后来的插队。"""
    pool = make_pool(tmp_path, factory, max_container=1, queue_timeout=5.0)
    await pool.acquire("thread-1")

    served: list[str] = []

    async def wait_for(thread_id: str) -> None:
        container = await pool.acquire(thread_id)
        served.append(container.id)

    first = asyncio.create_task(wait_for("thread-2"))
    await asyncio.sleep(0)
    second = asyncio.create_task(wait_for("thread-3"))
    await asyncio.sleep(0)

    await pool.release("thread-1")
    await first
    await pool.release("thread-2")
    await second

    assert served == ["fake-thread-2", "fake-thread-3"]
    await pool.aclose()


async def test_the_position_is_reported_every_time_it_changes(tmp_path: Path, factory: Factory) -> None:
    """教师要看见队伍在动，只推一次的话界面上是个静止的数字。"""
    pool = make_pool(tmp_path, factory, max_container=1, queue_timeout=5.0)
    await pool.acquire("thread-1")

    seen: list[int] = []

    async def wait_last() -> None:
        await pool.acquire("thread-4", on_queued=seen.append)

    front = asyncio.create_task(pool.acquire("thread-2"))
    await asyncio.sleep(0)
    middle = asyncio.create_task(pool.acquire("thread-3"))
    await asyncio.sleep(0)
    last = asyncio.create_task(wait_last())
    await asyncio.sleep(0)

    await pool.release("thread-1")
    await front
    await pool.release("thread-2")
    await middle
    await pool.release("thread-3")
    await last

    assert seen == [3, 2, 1]
    await pool.aclose()


async def test_no_position_is_reported_when_a_container_is_available(tmp_path: Path, factory: Factory) -> None:
    """没排队就不该冒出一个 sandbox.queued 事件。"""
    pool = make_pool(tmp_path, factory)
    seen: list[int] = []

    await pool.acquire("thread-1", on_queued=seen.append)

    assert seen == []
    await pool.aclose()


async def test_waiting_too_long_raises_instead_of_hanging(tmp_path: Path, factory: Factory) -> None:
    """无限等待会让 run 永远挂着，还占着配额。"""
    pool = make_pool(tmp_path, factory, max_container=1, queue_timeout=0.05)
    await pool.acquire("thread-1")

    with pytest.raises(SandboxQueueTimeoutError):
        await pool.acquire("thread-2")
    await pool.aclose()


async def test_a_timed_out_waiter_leaves_the_queue(tmp_path: Path, factory: Factory) -> None:
    """走掉的人还留在队里，后面的人看到的排位就永远不对。"""
    pool = make_pool(tmp_path, factory, max_container=1, queue_timeout=0.05)
    await pool.acquire("thread-1")

    with pytest.raises(SandboxQueueTimeoutError):
        await pool.acquire("thread-2")

    seen: list[int] = []
    waiting = asyncio.create_task(pool.acquire("thread-3", on_queued=seen.append))
    await asyncio.sleep(0)
    await pool.release("thread-1")
    await waiting

    assert seen == [1]
    await pool.aclose()


async def test_a_cancelled_waiter_leaves_the_queue(tmp_path: Path, factory: Factory) -> None:
    pool = make_pool(tmp_path, factory, max_container=1, queue_timeout=5.0)
    await pool.acquire("thread-1")

    abandoned = asyncio.create_task(pool.acquire("thread-2"))
    await asyncio.sleep(0)
    abandoned.cancel()
    with pytest.raises(asyncio.CancelledError):
        await abandoned

    waiting = asyncio.create_task(pool.acquire("thread-3"))
    await asyncio.sleep(0)
    await pool.release("thread-1")
    container = await waiting

    assert container.id == "fake-thread-3"
    await pool.aclose()


# ------------------------------------------------------------------ idle 回收
async def test_an_idle_container_is_reclaimed_by_the_sweep(tmp_path: Path, factory: Factory) -> None:
    pool = make_pool(tmp_path, factory, idle_timeout=0.0)

    await pool.acquire("thread-1")
    await pool.release("thread-1")
    await pool.sweep()

    assert factory.made[0].stopped
    await pool.aclose()


async def test_the_sweep_leaves_busy_containers_alone(tmp_path: Path, factory: Factory) -> None:
    pool = make_pool(tmp_path, factory, idle_timeout=0.0)

    await pool.acquire("thread-1")
    await pool.sweep()

    assert not factory.made[0].stopped
    await pool.aclose()


async def test_the_sweep_keeps_containers_that_are_still_within_the_idle_window(
    tmp_path: Path, factory: Factory
) -> None:
    pool = make_pool(tmp_path, factory, idle_timeout=1800.0)

    await pool.acquire("thread-1")
    await pool.release("thread-1")
    await pool.sweep()

    assert not factory.made[0].stopped
    await pool.aclose()


# ------------------------------------------------------------------ 租约失效兜底
async def test_a_lease_nobody_touches_any_more_is_released(tmp_path: Path, factory: Factory) -> None:
    """持有方若在 acquire 与 release 之间崩溃，这个名额本会被永久占住。

    lease>0 的 slot 既不受 idle 回收管、也不会被淘汰，而崩掉的那一侧再也不会来
    release。没有兜底的话，一次崩溃就永久少一个沙箱名额。
    """
    clock = FakeClock()
    pool = make_pool(tmp_path, factory, idle_timeout=0.0, lease_timeout=1800.0, clock=clock)

    await pool.acquire("thread-1")
    clock.advance(1801)
    await pool.sweep()

    assert factory.made[0].stopped
    assert pool.size == 0
    await pool.aclose()


async def test_a_lease_that_is_still_being_used_survives(tmp_path: Path, factory: Factory) -> None:
    """跑着的 run 每次工具调用都会经 `current` 摸一次容器，那就是它还活着的证据。"""
    clock = FakeClock()
    pool = make_pool(tmp_path, factory, idle_timeout=0.0, lease_timeout=1800.0, clock=clock)

    await pool.acquire("thread-1")
    clock.advance(1801)
    pool.current("thread-1")
    await pool.sweep()

    assert not factory.made[0].stopped
    await pool.aclose()


async def test_touching_a_thread_without_a_container_is_harmless(tmp_path: Path, factory: Factory) -> None:
    pool = make_pool(tmp_path, factory)

    assert pool.current("never-acquired") is None

    await pool.aclose()


async def test_a_long_run_is_not_cut_off_by_the_default_lease_window(tmp_path: Path, factory: Factory) -> None:
    """默认窗口要远大于两次工具调用之间的间隔，否则兜底本身就成了故障源。"""
    pool = make_pool(tmp_path, factory, idle_timeout=0.0)

    await pool.acquire("thread-1")
    await pool.sweep()

    assert not factory.made[0].stopped
    await pool.aclose()


async def test_a_reclaimed_thread_gets_a_fresh_container_next_time(tmp_path: Path, factory: Factory) -> None:
    """回收只销毁容器，workspace 留在盘上 —— 下次重建后文件还在。"""
    pool = make_pool(tmp_path, factory, idle_timeout=0.0)

    first = await pool.acquire("thread-1")
    await pool.release("thread-1")
    await pool.sweep()
    second = await pool.acquire("thread-1")

    assert first is not second
    assert second.workspace == first.workspace  # type: ignore[attr-defined]
    await pool.aclose()


async def test_the_sweep_frees_a_slot_for_a_queued_request(tmp_path: Path, factory: Factory) -> None:
    pool = make_pool(tmp_path, factory, max_container=1, idle_timeout=0.0, queue_timeout=5.0)
    await pool.acquire("thread-1")
    await pool.release("thread-1")

    waiting = asyncio.create_task(pool.acquire("thread-2"))
    await asyncio.sleep(0)
    await pool.sweep()

    assert (await waiting).id == "fake-thread-2"
    await pool.aclose()


# ------------------------------------------------------------------ 健康检查
async def test_a_dead_container_is_replaced_instead_of_handed_out(tmp_path: Path, factory: Factory) -> None:
    """容器可能被 OOM killer 干掉，本进程收不到通知，只能在交出去之前问一次。"""
    pool = make_pool(tmp_path, factory)
    await pool.acquire("thread-1")
    await pool.release("thread-1")
    factory.made[0].broken = True

    container = await pool.acquire("thread-1")

    assert container is factory.made[1]
    assert len(factory.made) == 2
    await pool.aclose()


async def test_replacing_a_dead_container_does_not_leak_a_slot(tmp_path: Path, factory: Factory) -> None:
    pool = make_pool(tmp_path, factory, max_container=1)
    await pool.acquire("thread-1")
    await pool.release("thread-1")
    factory.made[0].broken = True

    await pool.acquire("thread-1")
    await pool.release("thread-1")
    await pool.acquire("thread-2")

    assert len(factory.made) == 3
    await pool.aclose()


# ------------------------------------------------------------------ 启动失败
async def test_a_failed_start_propagates_and_frees_the_slot(tmp_path: Path, factory: Factory) -> None:
    """镜像没构建这类失败要让调用方看见，但不能把名额一起漏掉。"""
    pool = make_pool(tmp_path, factory, max_container=1)

    def broken_factory(thread_id: str, workspace: Path) -> FakeContainer:
        container = factory(thread_id, workspace)
        container.start_error = "docker run 失败"
        return container

    pool_with_broken = make_pool(tmp_path, factory, max_container=1, container_factory=broken_factory)
    with pytest.raises(ContainerError):
        await pool_with_broken.acquire("thread-1")

    assert pool_with_broken.size == 0
    await pool.aclose()
    await pool_with_broken.aclose()


# ------------------------------------------------------------------ 关闭
async def test_closing_stops_every_container(tmp_path: Path, factory: Factory) -> None:
    pool = make_pool(tmp_path, factory)
    await pool.acquire("thread-1")
    await pool.acquire("thread-2")

    await pool.aclose()

    assert all(one.stopped for one in factory.made)
    assert pool.size == 0


async def test_releasing_an_unknown_thread_is_harmless(tmp_path: Path, factory: Factory) -> None:
    """执行器在 finally 里 release，而失败可能发生在 acquire 之前。"""
    pool = make_pool(tmp_path, factory)

    await pool.release("never-acquired")
    await pool.aclose()


async def test_the_background_sweeper_reclaims_without_any_new_request(tmp_path: Path, factory: Factory) -> None:
    """只在有新申请时才回收的话，「教师走了、容器还占着 2GB」这种情况永远等不到回收。"""
    pool = make_pool(tmp_path, factory, idle_timeout=0.0)
    await pool.acquire("thread-1")
    await pool.release("thread-1")

    pool.start_sweeper(interval=0.01)
    await asyncio.sleep(0.05)

    assert factory.made[0].stopped
    await pool.aclose()


async def test_starting_the_sweeper_twice_keeps_one_task(tmp_path: Path, factory: Factory) -> None:
    pool = make_pool(tmp_path, factory, idle_timeout=0.0)

    pool.start_sweeper(interval=0.01)
    pool.start_sweeper(interval=0.01)
    await pool.aclose()

    assert pool.size == 0


async def test_closing_stops_the_sweeper(tmp_path: Path, factory: Factory) -> None:
    """留着后台任务不停，进程就退不干净。"""
    pool = make_pool(tmp_path, factory, idle_timeout=0.0)
    pool.start_sweeper(interval=0.01)

    await pool.aclose()
    await pool.acquire("thread-1")
    await pool.release("thread-1")
    await asyncio.sleep(0.05)

    assert not factory.made[0].stopped
    await pool.aclose()


async def test_closing_releases_everyone_still_queued(tmp_path: Path, factory: Factory) -> None:
    """关池时还在排队的申请要收到取消，而不是挂到超时。"""
    pool = make_pool(tmp_path, factory, max_container=1, queue_timeout=5.0)
    await pool.acquire("thread-1")
    waiting = asyncio.create_task(pool.acquire("thread-2"))
    await asyncio.sleep(0)

    await pool.aclose()

    with pytest.raises(asyncio.CancelledError):
        await waiting


# ------------------------------------------------------------------ broker 重启认领
class Reclaimable(Factory):
    """认领用的假工厂，顺便记下被接管的容器 id。"""


async def test_reclaim_adopts_containers_left_by_a_previous_broker(
    tmp_path: Path, factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """容器带 --rm 但不是 broker 的子进程，broker 重启不会带走它们。

    不认领就是既占着内存又不在池账上的孤儿：新申请另起一个，旧的再没人回收。
    """
    monkeypatch.setattr("sandbox.pool.running_sandbox", lambda: {"thread-1": "abc123", "thread-2": "def456"})
    pool = make_pool(tmp_path, factory)

    await pool.reclaim()

    assert pool.size == 2
    assert {one.adopted for one in factory.made} == {"abc123", "def456"}
    await pool.aclose()


async def test_a_reclaimed_container_is_reused_instead_of_restarted(
    tmp_path: Path, factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """认领的意义就在这里：接着用，而不是再起一个把旧的晾在那。"""
    monkeypatch.setattr("sandbox.pool.running_sandbox", lambda: {"thread-1": "abc123"})
    pool = make_pool(tmp_path, factory)
    await pool.reclaim()

    await pool.acquire("thread-1")

    assert len(factory.made) == 1
    assert factory.made[0].start_count == 0
    await pool.aclose()


async def test_a_reclaimed_container_is_idle_and_sweepable(
    tmp_path: Path, factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """用着它的 run 随上一个 broker 一起没了，因此它现在是空闲的，该受 idle 回收管。"""
    monkeypatch.setattr("sandbox.pool.running_sandbox", lambda: {"thread-1": "abc123"})
    pool = make_pool(tmp_path, factory, idle_timeout=0.0)
    await pool.reclaim()

    await pool.sweep()

    assert pool.size == 0
    await pool.aclose()


async def test_reclaim_does_not_disturb_containers_already_in_the_pool(
    tmp_path: Path, factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """认领可能被重复调用，正在服务某个 run 的容器绝不能被顶掉。"""
    pool = make_pool(tmp_path, factory)
    await pool.acquire("thread-1")
    monkeypatch.setattr("sandbox.pool.running_sandbox", lambda: {"thread-1": "abc123"})

    await pool.reclaim()

    assert pool.size == 1
    assert factory.made[0].adopted is None
    await pool.aclose()


async def test_reclaim_on_a_clean_host_does_nothing(
    tmp_path: Path, factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("sandbox.pool.running_sandbox", lambda: {})
    pool = make_pool(tmp_path, factory)

    await pool.reclaim()

    assert pool.size == 0
    await pool.aclose()
