"""指标注册表的建立与文本导出。

**不用 `prometheus_client` 的默认注册表。** 那是一个模块级可变全局：谁 import 谁就往里
塞指标，测试之间互相污染，且同一个指标名注册两次会直接抛。显式建一个注册表传下去，
这两件事都不会发生。
"""

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, ProcessCollector, generate_latest

# 指标名前缀。平台自己的指标一律 `zuel_` 开头，与 Prometheus 自带的、
# 以及将来任何一个 exporter 的指标分得开
NAMESPACE = "zuel"

CONTENT_TYPE = CONTENT_TYPE_LATEST

# worker 暴露指标的端口。**api 与 broker 不需要这个** —— 它们本就是 HTTP 服务，
# 多挂一条路由即可；worker 不是，这是它唯一监听的端口。
# 9100 是 node_exporter 的地盘，往后挪一个
DEFAULT_WORKER_PORT = 9101


def create_registry() -> CollectorRegistry:
    """建一个只属于调用方的注册表，并带上本进程的资源占用。

    `ProcessCollector` 给的是进程自己的常驻内存、CPU 与打开的文件数。它几乎不要钱
    （抓取时才读 `/proc`），而「api 进程为什么越来越胖」这类问题没有它就只能靠 `top` 猜。

    Returns:
        可以直接往里注册指标的注册表。
    """
    registry = CollectorRegistry()
    ProcessCollector(registry=registry)
    return registry


def render(registry: CollectorRegistry) -> bytes:
    """把注册表里的指标渲染成 Prometheus 的文本格式。

    Args:
        registry: 要导出的注册表。

    Returns:
        可直接作为响应体的字节串，配 `CONTENT_TYPE`。
    """
    return generate_latest(registry)
