"""run 相关的端点：查状态、订阅事件流。"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, status
from fastapi.responses import StreamingResponse

from api.error import invalid, not_found
from api.platform import Platform, get_platform
from api.schema import RunResponse
from api.security import CurrentUser
from api.sse import heartbeat_stream
from event.model import RunCancelledData, RunCancelledEvent, now_ms
from log import run_context
from run.log import InvalidEventIdError, parse_event_id
from run.repository import Run

logger = logging.getLogger(__name__)

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
async def get_run(
    run_id: str,
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> RunResponse:
    """查一次 run 的当前状态。别人的 run 与不存在的 run 是同一个回答。"""
    run = await _require_run(platform, run_id, current.user_id)
    return RunResponse(id=run.id, thread_id=run.thread_id, status=run.status)


@router.get("/{run_id}/events")
async def stream_events(
    run_id: str,
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    """订阅一次 run 的事件流。

    带上 `Last-Event-ID` 就从那个 id 之后接着推，中间产生的事件全部补齐。
    流在 run 进入终态时自然结束。

    **越权检查在这一层，不在事件那一层**：`run_events` 是全库最大的表，
    唯一的查询模式是「按 run_id 顺序重放」，冗余一列 user_id 只为鉴权不划算。
    先确认这个 run 属于当前用户，再读它的事件。
    """
    run = await _require_run(platform, run_id, current.user_id)

    cursor = _cursor(last_event_id)
    # 断线重连整段都发生在 api 侧，worker 的日志里一个字都不会有。
    # 「教师说页面没动静」的第一问是「订阅连上了没、从哪个游标接的」，答案只在这里
    with run_context(run_id=run_id, thread_id=run.thread_id, user_id=current.user_id):
        logger.info("事件流已订阅：游标=%s", cursor or "从头")

    body = heartbeat_stream(platform.log.follow(run_id, after=cursor))
    return StreamingResponse(body, media_type=SSE_MEDIA_TYPE, headers=SSE_HEADER)


@router.post("/{run_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
async def cancel_run(
    run_id: str,
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> RunResponse:
    """请求停下一个还在跑的 run。

    **202 而不是 200**：api 停不了 worker —— 那在另一个进程里。这里能做的是立一个
    标志、把状态抢先改掉，worker 在自己的下一个 step 边界上收手。因此取消是**尽快**
    而不是**立刻**：正在进行的那次模型调用会跑完，它的 token 已经花掉了。

    **已经跑完的 run 取消一次是空操作，不是错误** —— 教师点「停止」的那一刻它可能
    刚好结束，那不该弹一个红框。
    """
    run = await _require_run(platform, run_id, current.user_id)

    # **标志先立、状态后改**：反过来的话有一瞬间状态已经是 cancelled、标志却还没到，
    # 而 worker 正好在那一瞬间查了标志，就会一路跑到底
    await platform.cancel.raise_flag(run_id)
    with run_context(run_id=run_id, thread_id=run.thread_id, user_id=current.user_id):
        if await platform.repository.cancel(run_id):
            await platform.log.append(RunCancelledEvent(ts=now_ms(), run_id=run_id, path=(), data=RunCancelledData()))
            logger.info("run 已被取消")
        else:
            logger.info("run 已经是终态，取消是空操作")

    # 回真实状态而不是一律回 cancelled：已经跑完的那一次并没有被取消，
    # 谎报会让前端把一次成功的分析显示成被中断
    current_run = await _require_run(platform, run_id, current.user_id)
    return RunResponse(id=current_run.id, thread_id=current_run.thread_id, status=current_run.status)


async def _require_run(platform: Platform, run_id: str, user_id: str) -> Run:
    """确认这个 run 存在**且属于当前用户**，否则 404。"""
    run = await platform.repository.get(run_id, user_id=user_id)
    if run is None:
        message = f"run 不存在：{run_id}"
        raise not_found(message)
    return run


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
