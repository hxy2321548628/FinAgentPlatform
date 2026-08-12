"""Prometheus 抓取端点。

**不在 `/api` 前缀下，也不要求登录** —— Prometheus 没有会话，给它发一份长期凭据
只是把同一个问题换个地方放。挡在外面的是 nginx：`location = /metrics` 直接 404，
只有同一个 compose 网络里的 Prometheus 直连 `api:8000` 才拿得到。

这条边界要认真看待：响应里带着**用户名与他今天烧掉的 token**。那与成本看板是同一份
数据，而看板那一侧是要管理员身份的。
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from api.platform import Platform, get_platform
from metric.exposition import CONTENT_TYPE, render
from metric.platform import collect_platform

router = APIRouter(tags=["metric"])


@router.get("/metrics")
async def read_metric(platform: Annotated[Platform, Depends(get_platform)]) -> Response:
    """现查一遍平台状态，按 Prometheus 的文本格式给出。"""
    registry = await collect_platform(
        runs=platform.repository,
        queue=platform.queue,
        report=platform.usage_report,
        now=datetime.now(UTC),
    )
    return Response(content=render(registry), media_type=CONTENT_TYPE)
