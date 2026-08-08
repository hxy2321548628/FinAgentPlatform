"""把结构化日志也送进可观测性后端。

**日志走 OTLP 而不是让某个 agent 去扒容器的 stdout。** 扒 stdout 要么给采集器挂
`/var/lib/docker/containers`（那是宿主机 root 才读得动的目录，等于给它开一道
本不需要的口子），要么装 docker 的日志驱动插件。而这些日志本来就是这三个进程
自己产生的，直接发出去更短。

**真正的好处是 trace 与日志自动对上**：OTel 的 handler 会把当前 span 的
trace_id 写进每条日志。于是在 Grafana 里点开一条 trace，可以直接跳到那一次 run
的日志；反过来看到一条报错，也能跳回它所在的那条 trace。这件事靠 grep 是做不到的。

stdout 那一路**原样保留**：`docker logs` 仍然看得到，Loki 挂了也不影响排障。
"""

import logging

from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource

from log import context


def install(*, resource: Resource, endpoint: str) -> None:
    """给根 logger 再挂一条通往 collector 的路。

    Args:
        resource: 服务标识，与 trace 用同一份 —— 两边的 `service.name` 不一致时，
            Grafana 里那条「从 trace 跳到日志」的链接会指向一个空结果。
        endpoint: OTel Collector 的 OTLP/HTTP 地址。
    """
    provider = LoggerProvider(resource=resource)
    provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter(endpoint=f"{endpoint}/v1/logs")))
    set_logger_provider(provider)

    handler = LoggingHandler(logger_provider=provider)
    handler.addFilter(_ContextFilter())
    logging.getLogger().addHandler(handler)


class _ContextFilter(logging.Filter):
    """把 `run_id` / `thread_id` / `user_id` 抄到记录上。

    **不抄的话它们到不了 Loki**：这三个值存在 `contextvars` 里，由 JSON 格式化器
    在渲染那一刻现取 —— 而 OTLP 这条路根本不经过格式化器，它读的是记录本身的属性。
    症状是「stdout 上有 run_id，Loki 里没有」，而 Loki 里没有就等于按 run 过滤不出东西。
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """永远放行，只是顺手补几个属性。"""
        for name, value in context().items():
            setattr(record, name, value)
        return True
