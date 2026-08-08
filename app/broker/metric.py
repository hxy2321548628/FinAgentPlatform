"""broker 的抓取端点：沙箱容器数与内存。

单独一个模块而不是塞进 `route.py`：那里是「8 个工具与沙箱的申请归还」，是 api 唯一
够得着 broker 的那组能力；这里是给 Prometheus 抓的运维端点，两者的调用方都不是同一个。

**broker 本就不对外暴露端口**（只在 compose 内部网络上监听），因此这个端点不必再挡一次。
"""

import asyncio

from fastapi import APIRouter, Response

from broker.runtime import BrokerDep
from metric.exposition import CONTENT_TYPE, render
from metric.sandbox import collect_sandbox

router = APIRouter(tags=["metric"])


@router.get("/metrics")
async def read_metric(broker: BrokerDep) -> Response:
    """现查一遍沙箱占用，按 Prometheus 的文本格式给出。

    **丢进线程池跑**：读内存要调 docker CLI，那是一次同步的进程调用，
    留在事件循环里等于每次抓取都把 broker 卡住 —— 而卡住的正是沙箱的申请与归还。
    """
    registry = await asyncio.to_thread(collect_sandbox, pool=broker.pool, memory=broker.memory)
    return Response(content=render(registry), media_type=CONTENT_TYPE)
