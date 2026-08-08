"""沙箱指标的测试。

**docker 读不到时那条序列该缺席，而不是变成 0** —— 这是这一步唯一真正危险的地方：
容量看板上「不知道占了多少」与「一点没占」长得一模一样，而后者的意思是「随便再开几个」。
"""

from prometheus_client import CollectorRegistry

from metric.sandbox import collect_sandbox
from sandbox.container import ContainerError

CONTAINER_METRIC = "zuel_sandbox_container"
MEMORY_METRIC = "zuel_sandbox_memory_byte"

USED_BYTE = 3 << 30


class FakePool:
    def __init__(self, size: int) -> None:
        self._size = size

    @property
    def size(self) -> int:
        return self._size


def broken() -> int:
    message = "docker 没起来"
    raise ContainerError(message)


def snapshot(*, size: int = 0, used: int = 0) -> CollectorRegistry:
    return collect_sandbox(pool=FakePool(size), memory=lambda: used)


def test_the_container_count_comes_from_the_pool() -> None:
    assert snapshot(size=3).get_sample_value(CONTAINER_METRIC) == 3


def test_the_memory_is_actual_usage_not_the_limit() -> None:
    """`--memory=2g` 是上限，按它推算容量会系统性低估还装得下几个沙箱。"""
    assert snapshot(size=2, used=USED_BYTE).get_sample_value(MEMORY_METRIC) == USED_BYTE


def test_an_empty_machine_reports_zero_rather_than_nothing() -> None:
    """一个沙箱都没跑是一个确切的答案，与「读不到」不同，要写出来。"""
    registry = snapshot()

    assert registry.get_sample_value(CONTAINER_METRIC) == 0
    assert registry.get_sample_value(MEMORY_METRIC) == 0


def test_a_broken_docker_leaves_the_memory_series_out() -> None:
    """读不到就整条不上报。写 0 等于在容量看板上宣布「内存全空」。"""
    registry = collect_sandbox(pool=FakePool(2), memory=broken)

    assert registry.get_sample_value(MEMORY_METRIC) is None
    # 容器数取自池自己的账，不受 docker 拖累 —— 两处分别来，一处坏了另一处照常
    assert registry.get_sample_value(CONTAINER_METRIC) == 2
