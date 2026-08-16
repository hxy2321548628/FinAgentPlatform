"""MCP 目录端点：教师侧的目录与申请，管理员侧的队列、批拒、启停与探活。

**审批人是 `reviewer` 与 `admin`，与 agent、skill 同一档**（2026-08-16 改）。此前
只有 admin 批得了，理由是「放行外网地址是安全边界决定，不是内容合规判断」——
那条线划在**资源类型**上，于是同一个人审得了提示词却审不了 MCP，而两者要看的
其实是同一件事：这份东西该不该让全平台用。

**边界改划在审核与运维之间**：批与拒（连同这份队列）是审核，`reviewer` 做得了；
启停与探活是运维，仍然只有 admin —— 它们改的是一个已放行的服务此刻通不通，
与「该不该放行」无关。`reviewer` 多拿一样就离 admin 的别名近一步。

**目录没有三档可见性。** 管理员放行了就人人可勾 —— 一条目录记录就是一个平台级的
外部服务，「只有某个课题组能用」这种需求出现之前不做那一层。

**这一族端点从不回凭据。** 库里存的本来就只有键名，值在 `.env` 里；这张表要被前端
读（目录卡片），凭据在里面就等于人人可读。
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status

from agent.circuit import McpCircuit
from agent.mcp import probe_mcp_server
from api.error import invalid, not_found
from api.platform import Platform, get_platform
from api.schema import (
    AdminMcpServerResponse,
    ApplyMcpRequest,
    DecideMcpRequest,
    McpProbeResponse,
    McpServerResponse,
    SetMcpEnabledRequest,
)
from api.security import AdminUser, CurrentUser, ReviewerUser
from preset.mcp import McpApplication, McpServer, McpTargetLoader
from preset.model import ResourceKind, ReviewStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mcp", tags=["mcp"])

MCP_NOT_FOUND_MESSAGE = "没有这个 MCP"

NAME_TAKEN_MESSAGE = "已经有一个同名的 MCP 了，换一个名字"

INVALID_URL_MESSAGE = "地址必须是 http:// 或 https:// 开头的完整 URL"

ALREADY_DECIDED_MESSAGE = "这条申请已经处理过了"

REASON_REQUIRED_MESSAGE = "拒绝必须写明理由，申请人要照着它改"

NOT_TOGGLEABLE_MESSAGE = "只有已放行的服务才能手动启停；待审的要先批，被拒的要重新申请"

# **D3 的硬闸门，不是提示。** 平台既不把 MCP 工具纳入 HITL 审批（F8），也不传幂等键
# （F9），而队列是至少一次投递 —— 崩溃恢复会让写操作执行两次，且没有人在中间看一眼。
# 这两条任一落地之前，声明有写操作的一律批不了。**这是本期唯一一条「不能靠人记住」
# 的规则**：把它做成闸门，「必须先重定 F8/F9」这件事就不会被悄悄跨过
WRITE_OPERATION_MESSAGE = (
    "声明有写操作的 MCP 一律不批：平台目前既不拦截审批也不传幂等键，"
    "而队列是至少一次投递 —— 崩溃恢复会让写操作执行两次，且没有人在中间看一眼。"
)

ALLOWED_SCHEME = ("http://", "https://")


@router.get("")
async def browse_catalog(
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> list[McpServerResponse]:
    """MCP 目录：**只有放行了的**，全平台可见可勾。"""
    return [_to_response(one) for one in await platform.mcp.list_catalog()]


@router.post("", status_code=status.HTTP_201_CREATED)
async def apply_for_mcp(
    request: ApplyMcpRequest,
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> McpServerResponse:
    """提一份申请。**建出来是待审状态，管理员放行之前谁都勾不上它。**

    Raises:
        ApiError: 地址不是 http(s)，或者已经有同名的了。
    """
    if not request.url.startswith(ALLOWED_SCHEME):
        raise invalid(INVALID_URL_MESSAGE)
    created = await platform.mcp.apply(
        McpApplication(
            name=request.name,
            description=request.description,
            url=request.url,
            transport=request.transport,
            credential_key=request.credential_key,
            tool_names=request.tool_names,
            latency_note=request.latency_note,
            stores_user_data=request.stores_user_data,
            sends_data_out=request.sends_data_out,
            has_write_operation=request.has_write_operation,
        ),
        submitted_by=current.user_id,
    )
    if created is None:
        raise invalid(NAME_TAKEN_MESSAGE)
    # 审核记录复用 `reviews`：谁提的、谁批的、什么时候、为什么拒，那张表本来就记这些
    await platform.review.submit(
        target_id=created.id,
        submitted_by=current.user_id,
        responsibility_confirmed=True,
        target_kind=ResourceKind.MCP,
    )
    return _to_response(created)


@router.get("/admin")
async def list_for_admin(
    current: ReviewerUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> list[AdminMcpServerResponse]:
    """管理员后台：待审、已上架、已停用、已拒全都看得见，带申请人与失败计数。"""
    servers = await platform.mcp.list_all()
    names = await platform.user.names([one.submitted_by for one in servers])
    circuit = _circuit(platform)
    return [
        AdminMcpServerResponse(
            **_to_response(one).model_dump(),
            submitted_by=one.submitted_by,
            submitter_name=names.get(one.submitted_by, ""),
            failure_count=await circuit.failure_count(one.id),
        )
        for one in servers
    ]


@router.post("/admin/{server_id}/decision", status_code=status.HTTP_202_ACCEPTED)
async def decide_application(
    server_id: str,
    request: DecideMcpRequest,
    current: ReviewerUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> AdminMcpServerResponse:
    """放行或拒绝一份申请。

    Raises:
        ApiError: 没有这条、已经处理过、拒绝时没写理由，或者它声明了写操作。
    """
    reason = None if request.reason is None else request.reason.strip()
    if not request.approved and not reason:
        raise invalid(REASON_REQUIRED_MESSAGE)

    found = await platform.mcp.get(server_id)
    if found is None:
        raise not_found(MCP_NOT_FOUND_MESSAGE)
    if request.approved and found.has_write_operation:
        raise invalid(WRITE_OPERATION_MESSAGE)

    if not await platform.mcp.decide(server_id, reviewer_id=current.user_id, approved=request.approved, reason=reason):
        raise invalid(ALREADY_DECIDED_MESSAGE)
    await _close_review(platform, server_id, approved=request.approved, reason=reason, admin_id=current.user_id)
    logger.info("MCP 审批：server_id=%s approved=%s by=%s", server_id, request.approved, current.user_id)
    return await _require_admin_view(platform, server_id)


@router.post("/admin/{server_id}/enabled", status_code=status.HTTP_202_ACCEPTED)
async def set_enabled(
    server_id: str,
    request: SetMcpEnabledRequest,
    current: AdminUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> AdminMcpServerResponse:
    """手动启停。**启用时把失败计数一并清零** —— 不清的话，恢复之后再失败一次就又停。

    Raises:
        ApiError: 没有这条，或者它还没放行 / 已经被拒。
    """
    if await platform.mcp.get(server_id) is None:
        raise not_found(MCP_NOT_FOUND_MESSAGE)
    reason = None if request.reason is None else request.reason.strip()
    if not await platform.mcp.set_enabled(server_id, enabled=request.enabled, reason=reason):
        raise invalid(NOT_TOGGLEABLE_MESSAGE)
    if request.enabled:
        await _circuit(platform).reset(server_id)
    logger.info("MCP 启停：server_id=%s enabled=%s by=%s", server_id, request.enabled, current.user_id)
    return await _require_admin_view(platform, server_id)


@router.post("/admin/{server_id}/probe")
async def probe(
    server_id: str,
    current: AdminUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> McpProbeResponse:
    """测试连接：真去连一次，拿到工具名就算通。

    **走的是装配同一条路与同一个熔断计数器**，因此这里连续失败 5 次一样会自动停用 ——
    另写一份连接逻辑的话，这个按钮验的就是一条没人走的路。

    Raises:
        ApiError: 没有这条记录。
    """
    found = await platform.mcp.get(server_id)
    if found is None:
        raise not_found(MCP_NOT_FOUND_MESSAGE)
    loader = McpTargetLoader(platform.mcp, platform.mcp_credentials)
    target = await loader.load_mcp_target(server_id)
    if target is None:
        raise not_found(MCP_NOT_FOUND_MESSAGE)

    circuit = _circuit(platform)
    found_names = await probe_mcp_server(target, recorder=circuit)
    declared = set(found.tool_names)
    actual = set(found_names or [])
    return McpProbeResponse(
        reachable=found_names is not None,
        tool_names=sorted(actual),
        declared_only=sorted(declared - actual) if found_names is not None else [],
        undeclared=sorted(actual - declared),
        failure_count=await circuit.failure_count(server_id),
    )


def _circuit(platform: Platform) -> McpCircuit:
    return McpCircuit(platform.cache, platform.mcp)


async def _close_review(
    platform: Platform,
    server_id: str,
    *,
    approved: bool,
    reason: str | None,
    admin_id: str,
) -> None:
    """把 `reviews` 里那条待审记录一并结掉，让审批留痕对得上。"""
    pending = [
        one
        for one in await platform.review.list_for_target([server_id], target_kind=ResourceKind.MCP)
        if one.status is ReviewStatus.PENDING
    ]
    for one in pending:
        await platform.review.decide(one.id, reviewer_id=admin_id, approved=approved, reason=reason)


async def _require_admin_view(platform: Platform, server_id: str) -> AdminMcpServerResponse:
    """回读而不是拿写入的返回值拼 —— 拼出来的那份迟早会漏掉后加的字段。"""
    found = await platform.mcp.get(server_id)
    if found is None:
        raise not_found(MCP_NOT_FOUND_MESSAGE)
    names = await platform.user.names([found.submitted_by])
    return AdminMcpServerResponse(
        **_to_response(found).model_dump(),
        submitted_by=found.submitted_by,
        submitter_name=names.get(found.submitted_by, ""),
        failure_count=await _circuit(platform).failure_count(server_id),
    )


def _to_response(server: McpServer) -> McpServerResponse:
    return McpServerResponse(
        id=server.id,
        name=server.name,
        description=server.description,
        url=server.url,
        transport=server.transport,
        # **只说配没配，绝不回值。** 键名同样不回 —— 它本身就是一条运维线索
        has_credential=server.credential_key is not None,
        tool_names=server.tool_names,
        latency_note=server.latency_note,
        stores_user_data=server.stores_user_data,
        sends_data_out=server.sends_data_out,
        has_write_operation=server.has_write_operation,
        status=server.status,
        disabled_reason=server.disabled_reason,
        created_at=server.created_at,
        updated_at=server.updated_at,
    )
