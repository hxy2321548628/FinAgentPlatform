"""run 相关的端点：查状态、订阅事件流。"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Header
from fastapi.responses import StreamingResponse

from api.error import invalid, not_found
from api.platform import Platform, get_platform
from api.schema import RunResponse
from api.sse import format_event
from run.log import InvalidEventIdError, parse_event_id

router = APIRouter(prefix="/runs", tags=["run"])

SSE_MEDIA_TYPE = "text/event-stream"

SSE_HEADER = {
    "Cache-Control": "no-cache",
    # Nginx 默认会攒够一整个缓冲区才往下发，流式输出会全部卡到响应结束。
    # 本期直接跑 uvicorn 用不上这一条，但它得跟着端点走，不然上了反代才发现。
    "X-Accel-Buffering": "no",
}


@router.get("/{run_id}")
async def get_run(run_id: str, platform: Annotated[Platform, Depends(get_platform)]) -> RunResponse:
    """查一次 run 的当前状态。"""
    run = platform.executor.get(run_id)
    if run is None:
        message = f"run 不存在：{run_id}"
        raise not_found(message)
    return RunResponse(id=run.id, thread_id=run.thread_id, status=run.status)


@router.get("/{run_id}/events")
async def stream_events(
    run_id: str,
    platform: Annotated[Platform, Depends(get_platform)],
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    """订阅一次 run 的事件流。

    带上 `Last-Event-ID` 就从那个 id 之后接着推，中间产生的事件全部补齐。
    流在 run 进入终态时自然结束。
    """
    if platform.executor.get(run_id) is None:
        message = f"run 不存在：{run_id}"
        raise not_found(message)

    cursor = _cursor(last_event_id)

    async def body() -> AsyncIterator[str]:
        # 长时间静默（例如排队等沙箱）时没有心跳，反代或浏览器可能先把连接掐掉。
        # 本期直连 uvicorn 且 curl 不会超时，上反代前须补一条注释行做心跳。
        async for logged in platform.log.follow(run_id, after=cursor):
            yield format_event(logged)

    return StreamingResponse(body(), media_type=SSE_MEDIA_TYPE, headers=SSE_HEADER)


def _cursor(last_event_id: str | None) -> str | None:
    """校验客户端给的游标。

    空串按「没传过」处理：浏览器首次连接不会带这个头，但中间的代理有时会补一个空值。
    """
    if not last_event_id:
        return None
    try:
        parse_event_id(last_event_id)
    except InvalidEventIdError as exc:
        raise invalid(str(exc)) from exc
    return last_event_id
