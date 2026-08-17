"""提交侧把 MCP 标识解析成快照引用。"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.app.agent.config import AgentConfig, McpReference
from src.app.agent.mcp import MAX_MCP_SERVER
from src.app.preset.mcp import McpServer, McpStatus, McpTransport
from src.app.preset.mcp_reference import McpReferenceError, resolve_mcp_references


def server(
    name: str,
    *,
    status: McpStatus = McpStatus.ENABLED,
    tool_names: list[str] | None = None,
) -> McpServer:
    now = datetime.now(UTC)
    return McpServer(
        id=uuid4().hex,
        name=name,
        description="",
        url="https://mcp.example.edu/mcp",
        transport=McpTransport.STREAMABLE_HTTP,
        credential_key=None,
        tool_names=["search_paper"] if tool_names is None else tool_names,
        latency_note="",
        stores_user_data=False,
        sends_data_out=True,
        has_write_operation=False,
        status=status,
        disabled_reason=None,
        submitted_by=uuid4().hex,
        reviewed_by=None,
        created_at=now,
        updated_at=now,
    )


class Resolver:
    def __init__(self, *servers: McpServer) -> None:
        self._servers = {one.id: one for one in servers}
        self.calls: list[str] = []

    async def get(self, server_id: str) -> McpServer | None:
        self.calls.append(server_id)
        return self._servers.get(server_id)


async def test_no_selection_touches_the_catalog_not_at_all() -> None:
    resolver = Resolver()

    config = await resolve_mcp_references(AgentConfig(), server_ids=[], resolver=resolver)

    assert config.mcps == []
    assert resolver.calls == []


async def test_a_selected_server_is_frozen_as_id_and_name() -> None:
    """能冻住的只有这两样 —— 那台机器明天返回什么，平台今天不知道。"""
    one = server("paper-search")

    config = await resolve_mcp_references(AgentConfig(), server_ids=[one.id], resolver=Resolver(one))

    assert config.mcps == [McpReference(server_id=one.id, name="paper-search")]


@pytest.mark.parametrize("status", [McpStatus.PENDING, McpStatus.DISABLED, McpStatus.REJECTED])
async def test_anything_but_enabled_is_unusable(status: McpStatus) -> None:
    one = server("paper-search", status=status)

    with pytest.raises(McpReferenceError, match="用不了"):
        await resolve_mcp_references(AgentConfig(), server_ids=[one.id], resolver=Resolver(one))


async def test_a_vanished_record_is_unusable() -> None:
    with pytest.raises(McpReferenceError, match="用不了"):
        await resolve_mcp_references(AgentConfig(), server_ids=[uuid4().hex], resolver=Resolver())


async def test_more_than_the_limit_is_refused_before_any_lookup() -> None:
    """超限当场拒，不先查一遍再拒 —— 那等于让一个坏请求打 N 次库。"""
    resolver = Resolver()

    with pytest.raises(McpReferenceError, match=str(MAX_MCP_SERVER)):
        await resolve_mcp_references(
            AgentConfig(), server_ids=[uuid4().hex for _ in range(MAX_MCP_SERVER + 1)], resolver=resolver
        )
    assert resolver.calls == []


async def test_the_agents_own_servers_and_this_rounds_are_merged() -> None:
    bundled = server("bundled")
    picked = server("picked")
    config = AgentConfig(mcps=[McpReference(server_id=bundled.id, name=bundled.name)])

    merged = await resolve_mcp_references(config, server_ids=[picked.id], resolver=Resolver(bundled, picked))

    assert [one.name for one in merged.mcps] == ["bundled", "picked"]


async def test_picking_what_the_agent_already_carries_does_not_double_count() -> None:
    bundled = server("bundled")
    config = AgentConfig(mcps=[McpReference(server_id=bundled.id, name=bundled.name)])

    merged = await resolve_mcp_references(config, server_ids=[bundled.id], resolver=Resolver(bundled))

    assert [one.name for one in merged.mcps] == ["bundled"]


async def test_the_union_is_capped_too() -> None:
    """Agent 自带三个、这一轮再勾一个，合起来就超了 —— 两侧都要数。"""
    bundled = [server(f"bundled-{index}") for index in range(MAX_MCP_SERVER)]
    picked = server("picked")
    config = AgentConfig(mcps=[McpReference(server_id=one.id, name=one.name) for one in bundled])

    with pytest.raises(McpReferenceError, match=str(MAX_MCP_SERVER)):
        await resolve_mcp_references(config, server_ids=[picked.id], resolver=Resolver(*bundled, picked))


async def test_a_declared_builtin_tool_name_is_refused() -> None:
    """这道检查会过期，因此装配层还要再剔一次 —— 但教师该当场知道。"""
    one = server("impostor", tool_names=["search_paper", "read_file"])

    with pytest.raises(McpReferenceError, match="read_file"):
        await resolve_mcp_references(AgentConfig(), server_ids=[one.id], resolver=Resolver(one))
