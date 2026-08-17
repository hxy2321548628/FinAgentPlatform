"""MCP 目录数据层的测试，连真 Postgres。"""

import logging
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.preset.mcp import McpApplication, McpRepository, McpStatus, McpTargetLoader, McpTransport
from app.user.repository import User


@pytest.fixture
def servers(live_engine: AsyncEngine) -> McpRepository:
    return McpRepository(live_engine)


def application(name: str, *, has_write_operation: bool = False) -> McpApplication:
    return McpApplication(
        name=name,
        description="校内论文库检索",
        url="https://mcp.example.edu/mcp",
        transport=McpTransport.STREAMABLE_HTTP,
        credential_key=None,
        tool_names=["search_paper"],
        latency_note="典型 1 秒，最坏 10 秒",
        stores_user_data=False,
        sends_data_out=True,
        has_write_operation=has_write_operation,
    )


async def test_a_new_application_waits_for_an_administrator(servers: McpRepository, owner: User) -> None:
    created = await servers.apply(application(f"paper-{uuid4().hex[:8]}"), submitted_by=owner.id)

    assert created is not None
    assert created.status is McpStatus.PENDING
    assert created.reviewed_by is None
    assert created.id not in [one.id for one in await servers.list_catalog()]


async def test_an_approved_server_shows_up_in_the_catalog(servers: McpRepository, owner: User) -> None:
    created = await servers.apply(application(f"paper-{uuid4().hex[:8]}"), submitted_by=owner.id)
    assert created is not None

    assert await servers.decide(created.id, reviewer_id=owner.id, approved=True, reason=None)

    listed = await servers.get(created.id)
    assert listed is not None
    assert listed.status is McpStatus.ENABLED
    assert listed.reviewed_by == owner.id
    assert created.id in [one.id for one in await servers.list_catalog()]


async def test_a_decision_only_lands_once(servers: McpRepository, owner: User) -> None:
    created = await servers.apply(application(f"paper-{uuid4().hex[:8]}"), submitted_by=owner.id)
    assert created is not None

    assert await servers.decide(created.id, reviewer_id=owner.id, approved=True, reason=None)
    assert not await servers.decide(created.id, reviewer_id=owner.id, approved=False, reason="改主意了")

    decided = await servers.get(created.id)
    assert decided is not None
    assert decided.status is McpStatus.ENABLED


async def test_a_rejected_name_can_be_applied_for_again(servers: McpRepository, owner: User) -> None:
    """重名只在没被拒的那些之间算数：一次被拒不该把名字永久占住。"""
    name = f"paper-{uuid4().hex[:8]}"
    first = await servers.apply(application(name), submitted_by=owner.id)
    assert first is not None
    assert await servers.apply(application(name), submitted_by=owner.id) is None

    assert await servers.decide(first.id, reviewer_id=owner.id, approved=False, reason="地址在校外且无凭据说明")
    again = await servers.apply(application(name), submitted_by=owner.id)

    assert again is not None
    assert again.id != first.id


async def test_a_pending_server_cannot_be_switched_on_by_hand(servers: McpRepository, owner: User) -> None:
    """手动启停只在 enabled / disabled 之间来回；对待审的启用等于绕过审批。"""
    created = await servers.apply(application(f"paper-{uuid4().hex[:8]}"), submitted_by=owner.id)
    assert created is not None

    assert not await servers.set_enabled(created.id, enabled=True, reason=None)

    still = await servers.get(created.id)
    assert still is not None
    assert still.status is McpStatus.PENDING


async def test_an_automatic_disable_writes_the_reason_and_only_lands_once(servers: McpRepository, owner: User) -> None:
    """并发的两条失败路径只该写一次库。"""
    created = await servers.apply(application(f"paper-{uuid4().hex[:8]}"), submitted_by=owner.id)
    assert created is not None
    await servers.decide(created.id, reviewer_id=owner.id, approved=True, reason=None)

    assert await servers.disable_for_failure(created.id, reason="连续失败 5 次")
    assert not await servers.disable_for_failure(created.id, reason="连续失败 5 次")

    disabled = await servers.get(created.id)
    assert disabled is not None
    assert disabled.status is McpStatus.DISABLED
    assert disabled.disabled_reason == "连续失败 5 次"
    assert created.id not in [one.id for one in await servers.list_catalog()]


async def test_a_manual_recovery_clears_the_reason(servers: McpRepository, owner: User) -> None:
    created = await servers.apply(application(f"paper-{uuid4().hex[:8]}"), submitted_by=owner.id)
    assert created is not None
    await servers.decide(created.id, reviewer_id=owner.id, approved=True, reason=None)
    await servers.disable_for_failure(created.id, reason="连续失败 5 次")

    assert await servers.set_enabled(created.id, enabled=True, reason=None)

    recovered = await servers.get(created.id)
    assert recovered is not None
    assert recovered.status is McpStatus.ENABLED
    assert recovered.disabled_reason is None


async def test_the_declarations_survive_a_round_trip(servers: McpRepository, owner: User) -> None:
    """四项声明要原样读得回来 —— 写操作那一项是硬闸门的唯一依据。"""
    created = await servers.apply(
        application(f"paper-{uuid4().hex[:8]}", has_write_operation=True), submitted_by=owner.id
    )
    assert created is not None

    stored = await servers.get(created.id)
    assert stored is not None
    assert stored.tool_names == ["search_paper"]
    assert stored.latency_note == "典型 1 秒，最坏 10 秒"
    assert stored.stores_user_data is False
    assert stored.sends_data_out is True
    assert stored.has_write_operation is True


async def test_the_administrator_sees_every_status(servers: McpRepository, owner: User) -> None:
    pending = await servers.apply(application(f"pending-{uuid4().hex[:8]}"), submitted_by=owner.id)
    rejected = await servers.apply(application(f"rejected-{uuid4().hex[:8]}"), submitted_by=owner.id)
    assert pending is not None and rejected is not None
    await servers.decide(rejected.id, reviewer_id=owner.id, approved=False, reason="不批")

    everything = {one.id for one in await servers.list_all()}

    assert {pending.id, rejected.id} <= everything


async def test_the_loader_hands_the_credential_value_not_the_key(servers: McpRepository, owner: User) -> None:
    """库里存键名、`.env` 里存值，两边只在 worker 进程内合起来。"""
    created = await servers.apply(
        McpApplication(
            name=f"market-{uuid4().hex[:8]}",
            description="行情",
            url="https://mcp.example.edu/mcp",
            transport=McpTransport.STREAMABLE_HTTP,
            credential_key="market-data",
            tool_names=["quote"],
            latency_note="1 秒",
            stores_user_data=False,
            sends_data_out=True,
            has_write_operation=False,
        ),
        submitted_by=owner.id,
    )
    assert created is not None
    await servers.decide(created.id, reviewer_id=owner.id, approved=True, reason=None)
    loader = McpTargetLoader(servers, {"market-data": "Bearer 真的凭据"})

    target = await loader.load_mcp_target(created.id)

    assert target is not None
    assert target.credential == "Bearer 真的凭据"
    assert target.enabled is True
    assert target.declared_tool_name == ["quote"]


async def test_a_missing_credential_is_logged_and_still_attempted(
    servers: McpRepository, owner: User, caplog: pytest.LogCaptureFixture
) -> None:
    """键名配了但 `.env` 里没有对应的值，是运维漏了一步 —— 不能静默当成无凭据服务。"""
    created = await servers.apply(
        McpApplication(
            name=f"market-{uuid4().hex[:8]}",
            description="行情",
            url="https://mcp.example.edu/mcp",
            transport=McpTransport.STREAMABLE_HTTP,
            credential_key="没配的键",
            tool_names=["quote"],
            latency_note="1 秒",
            stores_user_data=False,
            sends_data_out=True,
            has_write_operation=False,
        ),
        submitted_by=owner.id,
    )
    assert created is not None
    loader = McpTargetLoader(servers, {})

    with caplog.at_level(logging.WARNING, logger="app.preset.mcp"):
        target = await loader.load_mcp_target(created.id)

    assert target is not None
    assert target.credential is None
    assert any("凭据键" in one.getMessage() for one in caplog.records)


async def test_a_disabled_server_reaches_the_assembler_as_disabled(servers: McpRepository, owner: User) -> None:
    """装配层靠这一位决定「一次都不连」，因此停用必须当场生效。"""
    created = await servers.apply(application(f"paper-{uuid4().hex[:8]}"), submitted_by=owner.id)
    assert created is not None
    await servers.decide(created.id, reviewer_id=owner.id, approved=True, reason=None)
    await servers.disable_for_failure(created.id, reason="连续失败 5 次")

    target = await McpTargetLoader(servers, {}).load_mcp_target(created.id)

    assert target is not None
    assert target.enabled is False
    assert target.disabled_reason == "连续失败 5 次"


async def test_a_vanished_record_loads_as_nothing(servers: McpRepository) -> None:
    assert await McpTargetLoader(servers, {}).load_mcp_target(uuid4().hex) is None
