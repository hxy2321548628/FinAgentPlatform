"""沙箱的指标：容器数与它们吃掉的内存。

**只有 broker 答得出这两个数** —— 它是唯一持有 `docker.sock` 的进程。api 与 worker
想数容器就得先拿到那个套接字，而那正是 ADR-0004 拆出 broker 要挡住的事。

两个数**分别来自两处，且刻意不互相校正**：容器数取自池自己的账（池按它判还有没有名额），
内存取自 docker。两者对不上本身就是信息 —— 说明有容器死在池的账外，或者反过来。
"""

import logging
from collections.abc import Callable
from typing import Protocol

from prometheus_client import CollectorRegistry, Gauge

from metric.exposition import NAMESPACE, create_registry
from sandbox.container import ContainerError

logger = logging.getLogger(__name__)

MemoryReader = Callable[[], int]


class ContainerCountProtocol(Protocol):
    """数得出当前存活容器的能力。"""

    @property
    def size(self) -> int:
        """当前存活的容器数。"""
        ...


def collect_sandbox(*, pool: ContainerCountProtocol, memory: MemoryReader) -> CollectorRegistry:
    """现查一遍沙箱占用，装进一个新注册表。

    Args:
        pool: 沙箱池。
        memory: 合计常驻内存的读法，字节。

    Returns:
        填好的注册表，可直接渲染。
    """
    registry = create_registry()
    Gauge(
        "sandbox_container",
        "当前存活的沙箱容器数",
        namespace=NAMESPACE,
        registry=registry,
    ).set(pool.size)
    _fill_memory(registry, memory)
    return registry


def _fill_memory(registry: CollectorRegistry, memory: MemoryReader) -> None:
    """沙箱合计常驻内存。

    **docker 读不到时这条序列整个不出现，不写 0。** 「不知道」与「是 0」在容量看板上
    长得一模一样，而后者意味着「随便再开几个沙箱」—— 这正是最不该猜的地方。
    序列缺失在 Grafana 上是一段空白，一眼看得出来。
    """
    try:
        used = memory()
    except ContainerError:
        logger.warning("读不到沙箱内存，这一轮不上报", exc_info=True)
        return
    Gauge(
        "sandbox_memory_byte",
        "沙箱容器合计占用的常驻内存，字节。**是实际占用不是 --memory 上限**",
        namespace=NAMESPACE,
        registry=registry,
    ).set(used)
