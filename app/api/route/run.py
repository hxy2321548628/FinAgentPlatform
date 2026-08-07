"""run 相关的端点：查状态、订阅事件流。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header
from fastapi.responses import StreamingResponse

from api.error import invalid, not_found
from api.platform import Platform, get_platform
from api.schema import RunResponse
from api.sse import heartbeat_stream
from run.log import InvalidEventIdError, parse_event_id

router = APIRouter(prefix="/runs", tags=["run"])

SSE_MEDIA_TYPE = "text/event-stream"

SSE_HEADER = {
    "Cache-Control": "no-cache",
    # Nginx 默认会攒够一整个缓冲区才往下发，流式输出会全部卡到响应结束。
    # 反代那边也配了 proxy_buffering off，两处都留着：这一条跟着端点走，
    # 换个反代或多加一层缓存时不必再想起来改配置。
    "X-Accel-Buffering": "no",
}


@router.get("/{run_id}")
async def get_run(run_id: str, platform: Annotated[Platform, Depends(get_platform)]) -> RunResponse:
    """查一次 run 的当前状态。"""
    run = await platform.repository.get(run_id)
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
    if await platform.repository.get(run_id) is None:
        message = f"run 不存在：{run_id}"
        raise not_found(message)

    cursor = _cursor(last_event_id)
    body = heartbeat_stream(platform.log.follow(run_id, after=cursor))
    return StreamingResponse(body, media_type=SSE_MEDIA_TYPE, headers=SSE_HEADER)


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
