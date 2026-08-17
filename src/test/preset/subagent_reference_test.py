"""主智能体自带子智能体与本轮临时选择的合并规则。"""

from uuid import uuid4

import pytest

from app.agent.config import AgentConfig, SubagentReference
from app.agent.subagent import MAX_SUBAGENT
from app.preset.repository import ResolvedAgent
from app.preset.subagent_reference import SubagentReferenceError, resolve_subagent_references


class Resolver:
    """按标识返回预置 Agent 的窄测试替身。"""

    def __init__(self, agents: dict[str, ResolvedAgent]) -> None:
        self._agents = agents
        self.calls: list[tuple[str, str]] = []

    async def resolve(self, agent_id: str, *, user_id: str) -> ResolvedAgent | None:
        self.calls.append((agent_id, user_id))
        return self._agents.get(agent_id)


def resolved(name: str, *, subagents: list[SubagentReference] | None = None) -> ResolvedAgent:
    """建立一个已发布 Agent 引用。"""
    return ResolvedAgent(
        agent_id=uuid4().hex,
        name=name,
        version=1,
        system_prompt=f"{name} prompt",
        skill_refs=None,
        subagent_refs=subagents,
        mcp_refs=None,
    )


def reference(agent: ResolvedAgent) -> SubagentReference:
    return SubagentReference(agent_id=agent.agent_id, version=agent.version, name=agent.name)


async def test_agent_and_run_subagent_references_are_merged() -> None:
    bundled = resolved("volatility-expert")
    temporary = resolved("returns-expert")
    config = AgentConfig(subagents=[reference(bundled)])

    merged = await resolve_subagent_references(
        config,
        subagent_ids=[temporary.agent_id],
        user_id=uuid4().hex,
        resolver=Resolver({temporary.agent_id: temporary}),
    )

    assert merged.subagents == [reference(bundled), reference(temporary)]


async def test_the_same_frozen_reference_is_only_kept_once() -> None:
    agent = resolved("volatility-expert")
    config = AgentConfig(subagents=[reference(agent)])

    merged = await resolve_subagent_references(
        config,
        subagent_ids=[agent.agent_id],
        user_id=uuid4().hex,
        resolver=Resolver({agent.agent_id: agent}),
    )

    assert merged.subagents == [reference(agent)]


async def test_an_unavailable_subagent_fails_closed() -> None:
    with pytest.raises(SubagentReferenceError, match="现在用不了"):
        await resolve_subagent_references(
            AgentConfig(),
            subagent_ids=[uuid4().hex],
            user_id=uuid4().hex,
            resolver=Resolver({}),
        )


async def test_an_agent_with_subagents_cannot_be_selected_as_a_subagent() -> None:
    nested = resolved("nested")
    scene = resolved("scene", subagents=[reference(nested)])

    with pytest.raises(SubagentReferenceError, match="场景不能再作为子智能体"):
        await resolve_subagent_references(
            AgentConfig(),
            subagent_ids=[scene.agent_id],
            user_id=uuid4().hex,
            resolver=Resolver({scene.agent_id: scene}),
        )


async def test_two_different_subagents_cannot_share_a_name() -> None:
    bundled = resolved("same-name")
    temporary = resolved("same-name")

    with pytest.raises(SubagentReferenceError, match="同名子智能体"):
        await resolve_subagent_references(
            AgentConfig(subagents=[reference(bundled)]),
            subagent_ids=[temporary.agent_id],
            user_id=uuid4().hex,
            resolver=Resolver({temporary.agent_id: temporary}),
        )


async def test_the_combined_subagent_set_cannot_exceed_five() -> None:
    bundled = resolved("bundled")
    temporary = [resolved(f"temporary-{index}") for index in range(MAX_SUBAGENT)]

    with pytest.raises(SubagentReferenceError, match=f"最多挂 {MAX_SUBAGENT} 个"):
        await resolve_subagent_references(
            AgentConfig(subagents=[reference(bundled)]),
            subagent_ids=[one.agent_id for one in temporary],
            user_id=uuid4().hex,
            resolver=Resolver({one.agent_id: one for one in temporary}),
        )


async def test_more_than_five_temporary_ids_are_rejected_before_database_access() -> None:
    resolver = Resolver({})

    with pytest.raises(SubagentReferenceError, match=f"最多挂 {MAX_SUBAGENT} 个"):
        await resolve_subagent_references(
            AgentConfig(),
            subagent_ids=[uuid4().hex for _ in range(MAX_SUBAGENT + 1)],
            user_id=uuid4().hex,
            resolver=resolver,
        )

    assert resolver.calls == []
