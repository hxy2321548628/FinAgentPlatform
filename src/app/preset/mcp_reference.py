"""把提交配置中的 MCP 标识解析成快照里的目录引用。

**这一层是「列表过滤对了而提交侧忘了查」那个漏洞形状的守卫**，与 skill / 子智能体
两处同形：目录列表里没有的，这里也必须解析不出来。

**解析出来的引用冻不住行为**，只冻得住「用了哪一条目录记录」—— 那台机器明天返回
什么，平台今天不知道。因此这里做的四道检查（放行了没有、停用了没有、超没超上限、
撞没撞名）全都是**提交那一刻**的判断，而装配层还要再判一次状态：这两处不是重复，
中间隔着几分钟，服务可能正好在这期间被熔断掉。
"""

import logging
from typing import Protocol

from app.agent.config import AgentConfig, McpReference
from app.agent.mcp import MAX_MCP_SERVER, RESERVED_TOOL_NAME
from app.preset.mcp import McpServer, McpStatus

UNAVAILABLE_MESSAGE = "这个 MCP 现在用不了：可能还没被管理员放行，或者已经停用了。请重新选择"
TOO_MANY_MESSAGE = f"一次运行最多挂 {MAX_MCP_SERVER} 个 MCP"

logger = logging.getLogger(__name__)


class McpResolverProtocol(Protocol):
    """MCP 引用解析对目录层的全部要求。"""

    async def get(self, server_id: str) -> McpServer | None:
        """按标识读一条目录记录，含它此刻的状态。"""
        ...


class McpReferenceError(ValueError):
    """MCP 引用无法形成一份可执行快照。"""


async def resolve_mcp_references(
    config: AgentConfig,
    *,
    server_ids: list[str],
    resolver: McpResolverProtocol,
) -> AgentConfig:
    """解析本轮临时勾选的 MCP，并与主智能体自带引用取并集。

    Args:
        config: 已解析 agent 引用的运行配置。
        server_ids: 教师这一轮勾的 MCP 标识。
        resolver: MCP 目录层。

    Returns:
        带 MCP 快照的运行配置。

    Raises:
        McpReferenceError: 数量超限、没放行、已停用或工具名撞车。
    """
    bundled = config.mcps
    if not server_ids:
        return config
    if len(server_ids) > MAX_MCP_SERVER:
        raise McpReferenceError(TOO_MANY_MESSAGE)

    resolved: list[McpServer] = []
    for server_id in server_ids:
        one = await resolver.get(server_id)
        if one is None or one.status is not McpStatus.ENABLED:
            logger.info("MCP 引用解析失败：server_id=%s", server_id)
            raise McpReferenceError(UNAVAILABLE_MESSAGE)
        resolved.append(one)

    temporary = [McpReference(server_id=one.id, name=one.name) for one in resolved]
    references = _unique_references([*bundled, *temporary])
    if len(references) > MAX_MCP_SERVER:
        raise McpReferenceError(TOO_MANY_MESSAGE)

    reserved = _reserved_collision(resolved)
    if reserved is not None:
        raise McpReferenceError(f"这个 MCP 声明的工具与平台内置工具重名，用不了：{reserved}")

    return config.model_copy(update={"mcps": references})


def _unique_references(references: list[McpReference]) -> list[McpReference]:
    """按 `{server_id, name}` 取并集，并保持主智能体自带引用在前。"""
    unique: list[McpReference] = []
    seen: set[tuple[str, str]] = set()
    for reference in references:
        identity = (reference.server_id, reference.name)
        if identity not in seen:
            unique.append(reference)
            seen.add(identity)
    return unique


def _reserved_collision(servers: list[McpServer]) -> str | None:
    """上架清单里有没有与平台内置工具重名的。

    **这道检查会过期，因此它不是唯一的防线** —— 装配层拿到真实工具之后还要再剔一次。
    放在这里是为了让教师在勾选那一刻就知道，而不是跑完一次分析才发现工具没生效。
    """
    for server in servers:
        for tool_name in server.tool_names:
            if tool_name in RESERVED_TOOL_NAME:
                return tool_name
    return None
