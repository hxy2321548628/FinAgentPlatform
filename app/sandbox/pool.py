"""沙箱池：容器按 thread 复用，容器数有上限，超限排队。

四件事合在一个类里，因为它们共用同一份状态（哪些容器在、谁在用、谁在等）：

- **按 thread 复用**：同一会话的后续调用拿到同一个容器，装过的包与写过的文件都还在；
- **容器数上限**：容量瓶颈是宿主机内存，不是 CPU；
- **LRU 回收**：满了先淘汰最久没人用的，正在服务某个 run 的容器绝不动；
- **排队**：淘汰不出空位就排队等，而不是直接失败 —— 教师看到「前面还有 N 个」比看到报错好。

**容器在 run 开始时申请、run 结束时归还**，不是每次执行代码借还一次。沙箱本就按 thread
长驻（run 结束后还留一段 idle 时间才回收），提前几分钟申请对占用时长的影响可以忽略，
换来的是排队事件由执行器直接产生，不必让 backend 反过来认识事件层。
"""

import asyncio
import logging
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sandbox.container import (
    DEFAULT_IMAGE,
    ContainerProtocol,
    DockerContainer,
    Hardening,
    ManagedContainerProtocol,
)
from sandbox.path import thread_workspace

logger = logging.getLogger(__name__)

# 容器数上限。宿主机 64 GB、单沙箱 2 GB，理论上限约 24，留余量取 20
DEFAULT_MAX_CONTAINER = 20

DEFAULT_IDLE_TIMEOUT = 1800.0
DEFAULT_QUEUE_TIMEOUT = 600.0

# 后台扫描 idle 容器的间隔。远小于 idle_timeout 即可，精确度对回收没有意义
DEFAULT_SWEEP_INTERVAL = 60.0

type ContainerFactory = Callable[[Path], ManagedContainerProtocol]
type QueuePositionCallback = Callable[[int], None]


class SandboxQueueTimeoutError(RuntimeError):
    """排队等待沙箱超时。

    执行器把它转成 `run.failed` 且 `retryable=True` —— 这是资源不足而非请求有问题，
    过一会儿重试是有意义的。
    """


@dataclass
class _Slot:
    """池里的一个容器及其占用情况。"""

    container: ManagedContainerProtocol
    # 正在使用它的 run 数。大于 0 就不可被淘汰
    lease: int
    last_used: float


# 队列里靠身份区分申请，不比字段：两个申请的回调可能是同一个函数
@dataclass(eq=False)
class _Waiter:
    """一个在排队的申请。"""

    future: asyncio.Future[None]
    on_queued: QueuePositionCallback | None


class SandboxPool:
    """按 thread 复用容器，并在容器数达上限时排队。

    Args:
        workspace_root: 所有 thread 的 workspace 所在的根目录。
        image: 沙箱镜像。
        max_container: 同时存活的容器数上限。
        idle_timeout: 无人使用多久后回收，秒。
        queue_timeout: 排队等待的上限，秒。
        hardening: 容器的资源限额与隔离档位，不传则用默认值。
        container_factory: 造容器的方式，默认是 Docker。测试用它换成假容器。
    """

    def __init__(
        self,
        *,
        workspace_root: Path,
        image: str = DEFAULT_IMAGE,
        max_container: int = DEFAULT_MAX_CONTAINER,
        idle_timeout: float = DEFAULT_IDLE_TIMEOUT,
        queue_timeout: float = DEFAULT_QUEUE_TIMEOUT,
        hardening: Hardening | None = None,
        container_factory: ContainerFactory | None = None,
    ) -> None:
        self._root = workspace_root
        self._max_container = max_container
        self._idle_timeout = idle_timeout
        self._queue_timeout = queue_timeout
        self._factory = container_factory or (
            lambda workspace: DockerContainer(workspace=workspace, image=image, hardening=hardening)
        )

        self._slot: dict[str, _Slot] = {}
        self._queue: deque[_Waiter] = deque()
        # 已经许给排队者、但对方还没来得及把容器起起来的名额。
        # 不预留的话，被唤醒的申请重新拿锁之前，空位会被别的申请抢走。
        self._reserved = 0
        self._lock = asyncio.Lock()
        self._sweeper: asyncio.Task[None] | None = None

    @property
    def size(self) -> int:
        """当前存活的容器数。"""
        return len(self._slot)

    def _workspace_for(self, thread_id: str) -> Path:
        """给出容器要 bind-mount 的目录，不存在则创建。

        目录留给 Docker 创建会是 root 属主，而容器以宿主 uid 运行，写不进去。
        """
        workspace = thread_workspace(self._root, thread_id)
        workspace.mkdir(parents=True, exist_ok=True)
        return workspace

    async def acquire(self, thread_id: str, *, on_queued: QueuePositionCallback | None = None) -> ContainerProtocol:
        """取得一个 thread 的容器，必要时排队等待。

        Args:
            thread_id: 会话标识，同一会话复用同一个容器。
            on_queued: 排队时的排位回调，排位每变一次调一次。不排队则一次也不调。

        Returns:
            可执行命令的容器。用完必须 `release`。

        Raises:
            SandboxQueueTimeoutError: 排队超过上限。
            ContainerError: 容器启动失败。
            PathEscapeError: thread_id 会让 workspace 落到根目录之外。
        """
        workspace = self._workspace_for(thread_id)

        async with self._lock:
            container = await self._take(thread_id, workspace)
            if container is not None:
                return container
            waiter = _Waiter(future=asyncio.get_running_loop().create_future(), on_queued=on_queued)
            self._queue.append(waiter)
            self._announce()

        try:
            await asyncio.wait_for(waiter.future, self._queue_timeout)
        except TimeoutError:
            self._abandon(waiter)
            message = f"等待沙箱超过 {self._queue_timeout:.0f} 秒"
            raise SandboxQueueTimeoutError(message) from None
        except asyncio.CancelledError:
            self._abandon(waiter)
            raise

        async with self._lock:
            # 名额是 _pump 许给本申请的，无论接下来起容器成不成，都在这里一次性归还
            self._reserved -= 1
            return await self._start(thread_id, workspace)

    async def release(self, thread_id: str) -> None:
        """归还容器。容器不销毁，留给同一 thread 的后续 run 复用。

        Args:
            thread_id: 会话标识。未持有时什么都不做。
        """
        async with self._lock:
            slot = self._slot.get(thread_id)
            if slot is not None:
                slot.lease = max(0, slot.lease - 1)
                slot.last_used = time.monotonic()
            await self._pump()

    async def sweep(self) -> None:
        """回收 idle 超时的容器，并把腾出的名额分给排队者。"""
        async with self._lock:
            deadline = time.monotonic() - self._idle_timeout
            stale = [
                thread_id for thread_id, slot in self._slot.items() if slot.lease == 0 and slot.last_used <= deadline
            ]
            for thread_id in stale:
                logger.info("沙箱 idle 超时，回收容器：thread_id=%s", thread_id)
                await self._discard(thread_id)
            await self._pump()

    def start_sweeper(self, *, interval: float = DEFAULT_SWEEP_INTERVAL) -> None:
        """起一个后台任务定期回收 idle 容器，重复调用无效。

        不起它的话，容器只在有新申请时才会被淘汰 —— 而 idle 回收要防的恰恰是
        「没人再来申请，容器却一直占着内存」。

        Args:
            interval: 扫描间隔，秒。
        """
        if self._sweeper is None:
            self._sweeper = asyncio.create_task(self._sweep_forever(interval))

    async def aclose(self) -> None:
        """停掉后台任务、遣散排队者、销毁全部容器。"""
        if self._sweeper is not None:
            self._sweeper.cancel()
            await asyncio.gather(self._sweeper, return_exceptions=True)
            self._sweeper = None

        async with self._lock:
            while self._queue:
                self._queue.popleft().future.cancel()
            for thread_id in list(self._slot):
                await self._discard(thread_id)

    async def _take(self, thread_id: str, workspace: Path) -> ContainerProtocol | None:
        """在持锁状态下尝试立刻拿到容器，拿不到返回 None 表示要排队。"""
        slot = self._slot.get(thread_id)
        if slot is not None:
            # 探测要问 Docker，是一次子进程调用。放在 acquire 里而不是每次执行命令前，
            # 是因为 acquire 一个 run 只发生一次，几十毫秒可以忽略
            if await asyncio.to_thread(slot.container.alive):
                slot.lease += 1
                slot.last_used = time.monotonic()
                return slot.container
            logger.warning("沙箱容器已不在运行，重建：thread_id=%s", thread_id)
            await self._discard(thread_id)

        if not self._has_room() and not await self._evict_idle():
            return None
        return await self._start(thread_id, workspace)

    async def _start(self, thread_id: str, workspace: Path) -> ContainerProtocol:
        """在持锁状态下起一个容器并登记。

        docker run 要一秒多，持锁等于让并发的申请串行启动。这是刻意的：
        放开锁就得先占位再启动，失败回滚的分支比省下的这一秒贵。
        """
        container = self._factory(workspace)
        await asyncio.to_thread(container.start)
        self._slot[thread_id] = _Slot(container=container, lease=1, last_used=time.monotonic())
        return container

    async def _discard(self, thread_id: str) -> None:
        """在持锁状态下销毁一个容器。workspace 留在盘上，下次重建后文件还在。"""
        slot = self._slot.pop(thread_id, None)
        if slot is not None:
            await asyncio.to_thread(slot.container.stop)

    async def _evict_idle(self) -> bool:
        """在持锁状态下淘汰最久没人用的空闲容器，没有可淘汰的返回 False。"""
        idle = [(slot.last_used, thread_id) for thread_id, slot in self._slot.items() if slot.lease == 0]
        if not idle:
            return False
        _, victim = min(idle)
        logger.info("沙箱数达上限，淘汰最久未用的容器：thread_id=%s", victim)
        await self._discard(victim)
        return True

    async def _pump(self) -> None:
        """在持锁状态下，把能满足的排队申请依次放行。"""
        while self._queue and (self._has_room() or await self._evict_idle()):
            self._reserved += 1
            self._queue.popleft().future.set_result(None)
        self._announce()

    def _has_room(self) -> bool:
        return len(self._slot) + self._reserved < self._max_container

    def _announce(self) -> None:
        """把当前排位推给还在队里的申请。排位每变一次推一次，前端才看得到队伍在动。"""
        for position, waiter in enumerate(self._queue, start=1):
            if waiter.on_queued is not None:
                waiter.on_queued(position)

    def _abandon(self, waiter: _Waiter) -> None:
        """申请方不等了：把它摘出队列。

        全是同步操作，因此不需要持锁 —— 事件循环单线程，中间不会有别的协程插进来。
        极小概率上名额已经许给了它（放行与超时同时发生），那就把名额还回去；
        不在这里唤醒下一个，留给下一次 release 或 sweep —— 为此起个游离任务不值得。
        """
        if waiter.future.done() and not waiter.future.cancelled():
            self._reserved -= 1
        elif waiter in self._queue:
            self._queue.remove(waiter)
        self._announce()

    async def _sweep_forever(self, interval: float) -> None:
        while True:
            await asyncio.sleep(interval)
            await self.sweep()
