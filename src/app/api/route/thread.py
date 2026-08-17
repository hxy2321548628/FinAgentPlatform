"""会话相关的端点：开会话、翻列表、改、删、提交分析、翻历史。

**每一个都先用当前用户去查这个会话**，查不到就是 404 —— 不存在与不属于你在这里
是同一个回答。过滤条件长在仓储里，这里没有一句「鉴权判断」，越权返 404 是那层过滤的
副产品而不是额外工作。

**聊天历史是两段拼起来的**：这里的 `GET /{id}/runs` 给出「问了什么、结局如何」，
每一轮的过程由 `GET /runs/{id}/events` 逐个重放（已终态的 run 会先补齐历史再自然结束）。
不把事件塞进列表，是因为一轮几百条，打开会话会变成一次几 MB 的下载。

会话工作目录里的文件是另一个模块（`route/file.py`），它复用这里的 `require_thread`：
「这个会话是不是你的」只该有一份判定。
"""

import logging
from collections.abc import Awaitable
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from pydantic import ValidationError

from src.app.agent.config import effective_config
from src.app.api.error import concurrency_limit, invalid, not_found, quota_exceeded, unauthenticated
from src.app.api.platform import Platform, get_platform
from src.app.api.schema import (
    RunHistoryResponse,
    RunPageResponse,
    RunRequest,
    RunResponse,
    ThreadDetailResponse,
    ThreadPageResponse,
    ThreadResponse,
    UpdateThreadRequest,
)
from src.app.api.security import UNAUTHENTICATED_MESSAGE, CurrentUser
from cursor import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, CursorError, Page
from src.app.event.model import RunStatus
from src.app.preset.mcp_reference import McpReferenceError, resolve_mcp_references
from src.app.preset.reference import ReferenceUnavailableError, resolve_reference
from src.app.preset.skill_reference import SkillReferenceError, resolve_skill_references
from src.app.preset.subagent_reference import SubagentReferenceError, resolve_subagent_references
from src.app.run.approval import DEFAULT_PENDING_LIMIT, pending_count
from src.app.sandbox.remote import BrokerError
from src.app.thread.repository import Thread

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/threads", tags=["thread"])

CursorParam = Annotated[str | None, Query(description="上一页给的 next_cursor，原样带回来。不传即从头")]

LimitParam = Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE, description="一页几条")]

SearchParam = Annotated[
    str | None,
    Query(min_length=1, max_length=64, description="按标题模糊搜索（大小写不敏感）；不传则全部"),
]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_thread(
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> ThreadResponse:
    """开一个新会话。

    **先落表、后建目录**：表是「会话存不存在」的权威，目录是它的副产品。
    目录建失败就把那一行删掉 —— 留着就是个查得到却用不了的半个会话。

    标题是空的，等第一次提问之后由一次轻量模型调用填上。
    """
    thread = await platform.thread.create(user_id=current.user_id)
    try:
        await platform.workspace.create(thread.id)
    except Exception:
        logger.warning("会话目录没建成，回滚这一行：thread_id=%s", thread.id, exc_info=True)
        # 硬删而不是打标记：这一行刚建出来，还没有任何 run 指着它
        await platform.thread.purge(thread.id, user_id=current.user_id)
        raise
    return _to_response(thread)


@router.get("")
async def list_thread(
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
    cursor: CursorParam = None,
    limit: LimitParam = DEFAULT_PAGE_SIZE,
    q: SearchParam = None,
) -> ThreadPageResponse:
    """我的会话，最近活动的在前。

    **游标分页而不是 offset**：这一页按 `updated_at` 排，而那个字段会因为新提问而变动 ——
    翻页途中若有会话被顶到首页，offset 会漏掉或重复条目，且不报错。

    `q` 只匹配标题：会话没有正文索引，全量搜索成本与收益都不划算。
    """
    page = await _paged(platform.thread.list(user_id=current.user_id, cursor=cursor, limit=limit, query=q))
    # 每个会话「还在跑的 run」批量查一次（见 RunRepository.live_statuses），
    # 列表要显示进行中状态点，而它属于 runs 表
    live = await platform.repository.live_statuses([one.id for one in page.items], user_id=current.user_id)
    return ThreadPageResponse(
        items=[_to_response(one, live_status=live.get(one.id)) for one in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/{thread_id}")
async def get_thread(
    thread_id: str,
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> ThreadDetailResponse:
    """一个会话的详情。别人的会话与不存在的会话是同一个回答。"""
    thread = await require_thread(platform, thread_id, current.user_id)
    live = await platform.repository.live_statuses([thread.id], user_id=current.user_id)
    return ThreadDetailResponse(
        id=thread.id,
        title=thread.title,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
        live_run_status=live.get(thread.id),
        agent_config=thread.agent_config,
    )


@router.patch("/{thread_id}")
async def update_thread(
    thread_id: str,
    request: UpdateThreadRequest,
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> ThreadDetailResponse:
    """改会话的标题或 agent 配置。

    **两个字段各自可选**，都不传时这一次调用只把会话顶回列表首位 —— 那是合法的，
    不必为它专门报错。
    """
    changed = await platform.thread.update(
        thread_id,
        user_id=current.user_id,
        title=request.title,
        agent_config=None if request.agent_config is None else request.agent_config.model_dump(exclude_none=True),
    )
    if changed is None:
        raise not_found(f"会话不存在：{thread_id}")
    return ThreadDetailResponse(
        id=changed.id,
        title=changed.title,
        created_at=changed.created_at,
        updated_at=changed.updated_at,
        agent_config=changed.agent_config,
    )


@router.delete("/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_thread(
    thread_id: str,
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> None:
    """删掉一个会话：从列表里消失，工作目录与沙箱一并销毁。

    **表先于目录，与建会话正好对称**：表是权威，先把行标记掉，再让 broker 去销毁
    容器与目录。反过来的话，有一瞬间目录已经没了而会话还查得到 —— 那是个打得开
    却读不了的会话。

    **`runs` 那几行留着。** 它是成本账本，删掉等于往历史里挖一个洞；教师要的是
    「从我的列表里消失、别再占磁盘」，那两件这里都做到了。

    **销毁失败仍答 204。** 对教师来说这个会话确实已经删了（列表里没有了），
    报 500 只会让他再点一次，而第二次得到的是 404。留下的孤儿目录是运维问题，
    日志里有，磁盘巡检看得见。
    """
    await require_thread(platform, thread_id, current.user_id)
    await platform.thread.delete(thread_id, user_id=current.user_id)

    try:
        await platform.workspace.destroy(thread_id)
    except BrokerError:
        logger.error(
            "会话已删但沙箱与目录没销毁成，留下一个孤儿目录：thread_id=%s user_id=%s",
            thread_id,
            current.user_id,
            exc_info=True,
        )


@router.post("/{thread_id}/runs", status_code=status.HTTP_202_ACCEPTED)
async def submit_run(
    thread_id: str,
    request: RunRequest,
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
    background: BackgroundTasks,
) -> RunResponse:
    """提交一次分析，立刻返回。

    执行要几分钟到几十分钟，进度通过订阅事件流看，不在这个响应里等。

    **两道闸都在这里关**：token 日配额与并发 run 上限都只在「新开一次执行」时有意义，
    挂到路由器上会让查状态、订阅事件也被它们拦住。

    **起标题挂在响应之后**：那是一次模型往返，一两秒 —— 放进这条路径就等于让每次
    提交都慢那么多，而这个端点的全部意义就是立刻返回。
    """
    thread = await require_thread(platform, thread_id, current.user_id)
    await _require_quota(platform, current.user_id)

    try:
        effective = effective_config(thread_config=thread.agent_config, override=request.agent_config)
    except ValidationError as exc:
        # P6 之前 thread 接口允许任意 JSON，历史行可能带着已不支持的键。
        # 读会话仍原样返回，但提交不能静默忽略它，更不能漏成无上下文的 500。
        raise invalid(f"会话默认的 agent 配置无效，请重新保存配置：{exc}") from exc

    try:
        # **引用在这一刻被解析掉，之后再没人碰它。** 到 worker 领到任务之间可能隔几分钟，
        # 那期间作者随时可能撤回共享或发新版本 —— 在执行侧解析，同一次提交的结果就取决于
        # worker 什么时候有空
        resolved_agent = await resolve_reference(effective, user_id=current.user_id, resolver=platform.agent)
        resolved = await resolve_skill_references(
            resolved_agent,
            skill_ids=effective.skills,
            user_id=current.user_id,
            resolver=platform.skill,
        )
        resolved = await resolve_subagent_references(
            resolved,
            subagent_ids=effective.subagents,
            user_id=current.user_id,
            resolver=platform.agent,
        )
        resolved = await resolve_mcp_references(
            resolved,
            server_ids=effective.mcps,
            resolver=platform.mcp,
        )
    except (ReferenceUnavailableError, SkillReferenceError, SubagentReferenceError, McpReferenceError) as exc:
        # **不静默回退默认提示词。** 回退跑得完、不报错，唯一的症状是回答变了味
        raise invalid(str(exc)) from exc

    # 两类引用都完整解析并通过撞名/数量校验之后才记调用，避免一个坏 Skill 让前面的
    # 引用计数增长，而这次 run 实际上一行都没有创建。
    if resolved.agent_id is not None:
        await platform.agent.count_call(resolved.agent_id)
    for skill in resolved.skills or []:
        await platform.skill.count_call(skill.skill_id)
    for subagent in resolved.subagents:
        await platform.agent.count_call(subagent.agent_id)

    run = await platform.submitter.submit(
        thread_id=thread_id,
        content=request.content,
        user_id=current.user_id,
        agent_config=resolved,
    )
    # 列表按最后活动排序，靠的就是这一下。不推的话，一个用了半年的会话仍旧沉在底下
    await platform.thread.touch(thread_id, user_id=current.user_id)

    # 只在还没有标题时才花这一次调用。生成那一侧会再查一遍 —— 那道检查防的是
    # 另一件事（模型往返期间教师自己改了名），两道都要
    if not thread.title:
        background.add_task(platform.title.compose, thread_id, user_id=current.user_id, content=request.content)
    return RunResponse(
        id=run.id,
        thread_id=run.thread_id,
        status=run.status,
        agent_config=run.agent_config.model_dump(exclude_none=True),
    )


@router.get("/{thread_id}/runs")
async def list_run(
    thread_id: str,
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
    cursor: CursorParam = None,
    limit: LimitParam = DEFAULT_PAGE_SIZE,
) -> RunPageResponse:
    """这个会话里的历次分析，**最近的在前**。

    这是聊天历史的骨架：每一条给出教师问了什么与那一轮的结局，过程用它的 `id` 去
    `GET /runs/{id}/events` 重放 —— 已经结束的 run 会先补齐全部历史再自然收尾，
    因此同一条订阅端点既服务「正在跑」也服务「翻旧账」。

    **倒序**是因为教师打开会话先看最近几轮，往上滚才翻更早的；前端把这一页倒过来渲染。
    """
    await require_thread(platform, thread_id, current.user_id)

    page = await _paged(
        platform.repository.list_by_thread(thread_id, user_id=current.user_id, cursor=cursor, limit=limit)
    )
    return RunPageResponse(
        items=[
            RunHistoryResponse(
                id=one.id,
                status=one.status,
                content=one.content,
                error_code=one.error_code,
                error_message=one.error_message,
                started_at=one.started_at,
                ended_at=one.ended_at,
                agent_config=one.agent_config.model_dump(exclude_none=True),
            )
            for one in page.items
        ],
        next_cursor=page.next_cursor,
    )


async def _paged[Item](call: Awaitable[Page[Item]]) -> Page[Item]:
    """跑一次翻页查询，把游标那一侧的失败翻成对外的回答。

    Raises:
        ApiError: 游标不合法（422）。当成「从头开始」是错的 —— 那会让客户端收到
            一整页重复数据，而它看不出发生了什么。
    """
    try:
        return await call
    except CursorError as exc:
        raise invalid(str(exc)) from exc


def _to_response(thread: Thread, *, live_status: RunStatus | None = None) -> ThreadResponse:
    return ThreadResponse(
        id=thread.id,
        title=thread.title,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
        live_run_status=live_status,
    )


async def _require_quota(platform: Platform, user_id: str) -> None:
    """确认这个用户还有额度可用，没有就 429。

    **两道闸的 code 不同**，因为前端要做的事完全不同：配额耗尽该提示明天再来，
    并发超限该提示先等已有任务跑完。

    Raises:
        ApiError: 今日配额已用尽，或同时在跑的 run 已达上限。
    """
    user = await platform.user.get(user_id)
    if user is None:
        # session 还在、账号已经没了。当作未登录处理比放行安全
        raise unauthenticated(UNAUTHENTICATED_MESSAGE)

    allowance = platform.policy.allow(
        role=user.role,
        token_daily=user.quota_tokens_daily,
        concurrent_run=user.quota_concurrent_runs,
    )

    # **`None` 是「不限」，不是「上限为 0」** —— 当前只有 admin 这一档，
    # 它是平台的运维出口，被自己的闸门挡住时连「查为什么」也一起做不了了
    if allowance.token_daily is not None:
        used = await platform.usage.token_today(user_id)
        if used >= allowance.token_daily:
            # **不再 `astimezone()` 一次**：那一步转的是进程时区，容器里就是 UTC，
            # 于是印出来的「00:00 重置」实际是北京时间早上八点
            reset = platform.usage.next_reset().strftime("%m-%d %H:%M")
            logger.info("配额耗尽，拒绝提交：user_id=%s used=%d limit=%d", user_id, used, allowance.token_daily)
            raise quota_exceeded(f"今日 token 配额已用尽（{used}/{allowance.token_daily}），{reset} 重置")

    active = await platform.usage.active_run(user_id)
    if active >= allowance.concurrent_run:
        logger.info("并发超限，拒绝提交：user_id=%s active=%d limit=%d", user_id, active, allowance.concurrent_run)
        raise concurrency_limit(f"同时在跑的分析已达上限（{active}/{allowance.concurrent_run}），请等其中一个跑完")

    # **待审批数与并发配额是两回事**：等人确认既不占 worker 也不占沙箱，因此不占并发；
    # 但「不占资源」不等于「可以无限堆积」。这是防堆积的那道闸，与资源无关
    waiting = await pending_count(platform.engine, user_id)
    if waiting >= DEFAULT_PENDING_LIMIT:
        logger.info("待审批堆积，拒绝提交：user_id=%s waiting=%d", user_id, waiting)
        raise concurrency_limit(f"还有 {waiting} 个分析在等你确认，先处理掉再提交新的")


async def require_thread(platform: Platform, thread_id: str, user_id: str) -> Thread:
    """确认这个会话存在**且属于当前用户**，否则 404。

    **查的是表不是目录**：目录没有归属信息，让它当权威等于把越权检查建在一个
    不知道谁是主人的东西上。
    """
    thread = await platform.thread.get(thread_id, user_id=user_id)
    if thread is None:
        message = f"会话不存在：{thread_id}"
        raise not_found(message)
    return thread
