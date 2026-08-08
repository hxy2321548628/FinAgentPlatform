"""追踪的开关与探针安装。

**分成两步，因为它们能做的时机不同**：

- `instrument()` 只把探针挂上，不碰配置。必须在应用开始服务**之前**调用 ——
  Starlette 的中间件栈一旦建起来就加不进新的中间件了。
- `configure()` 才真正接上后端，它要读配置，因此只能在 lifespan 里调。

没配后端时探针照样在，只是每个 span 都落到 OTel 的空实现上 —— 那几乎不要钱，
而且省掉了「测试里要不要装探针」这个本不该存在的分支。
"""

import logging
from typing import Literal

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger(__name__)

# 三个进程在 trace 里的名字。Grafana 的服务图与「这一段是谁的」全靠它
API_SERVICE = "zuel-api"
BROKER_SERVICE = "zuel-broker"
WORKER_SERVICE = "zuel-worker"

# 抓取端点自己不该产生 span。**不排除的话，每 15 秒一次的抓取会在 Tempo 里
# 刷出一条 trace**，而那些 trace 里除了「Prometheus 来过」什么都没有 ——
# 真正要找的那条会被埋在里面
EXCLUDED_URL = "metrics"

# ASGI 探针默认给每次 `receive` / `send` 各开一个 span。**一次请求因此从 1 个变成 4 个**，
# 而它们说的都是同一件事。SSE 那条更夸张：一个几十分钟的事件流每推一个事件就多一个 span，
# 一次分析能刷出几百个 —— 要找的那条 trace 会被自己的噪声埋掉
EXCLUDED_SPAN: list[Literal["receive", "send"]] = ["receive", "send"]


def instrument(app: FastAPI) -> None:
    """给一个 FastAPI 应用与本进程的 httpx 客户端挂上探针。

    **必须在应用开始服务之前调用。**

    Args:
        app: 要观测的应用。
    """
    FastAPIInstrumentor.instrument_app(app, excluded_urls=EXCLUDED_URL, exclude_spans=EXCLUDED_SPAN)
    _instrument_client()


def instrument_client() -> None:
    """只挂 httpx 探针。worker 没有 FastAPI 应用，走这一条。"""
    _instrument_client()


def configure(*, service_name: str, endpoint: str) -> None:
    """把 span 接到 OTel Collector 上。

    **端点留空即整个关掉**，与「没配磁盘配额就不设配额」同一个规矩：
    开发机上直接跑 uvicorn 时没有 collector，接不上就该是不接，而不是每条 span
    都去连一个不存在的地址、再吞掉一串连接错误。

    Args:
        service_name: 本进程在 trace 里的名字。
        endpoint: OTel Collector 的 OTLP/HTTP 地址，形如 http://otel-collector:4318。
    """
    if not endpoint:
        logger.info("未配 OTel 端点，本进程不上报 trace")
        return
    provider = TracerProvider(resource=Resource.create({SERVICE_NAME: service_name}))
    # 批量导出：一次分析产生几十上百个 span，逐个同步发等于把网络往返算进
    # 被观测的代码里 —— 那会让「观测」本身成为耗时的一部分
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")))
    trace.set_tracer_provider(provider)
    logger.info("trace 已接上：service=%s endpoint=%s", service_name, endpoint)


def _instrument_client() -> None:
    """挂 httpx 探针。**重复挂是无害的**，第二次会被 OTel 自己挡掉。

    这个探针就是 api / worker → broker 那两段能自动串起来的全部原因：
    它把 traceparent 放进请求头，broker 那侧的 FastAPI 探针再把它取出来。
    """
    HTTPXClientInstrumentor().instrument()
