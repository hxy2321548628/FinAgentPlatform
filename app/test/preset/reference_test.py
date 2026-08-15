"""主智能体引用解析会把其冻结配置完整带进 run。"""

from uuid import uuid4

from agent.config import AgentConfigRequest, SubagentReference
from preset.reference import resolve_reference
from preset.repository import ResolvedAgent


class Resolver:
    def __init__(self, agent: ResolvedAgent) -> None:
        self._agent = agent

    async def resolve(self, agent_id: str, *, user_id: str) -> ResolvedAgent | None:
        return self._agent if agent_id == self._agent.agent_id else None


async def test_a_main_agent_carries_its_frozen_subagents_into_the_run_config() -> None:
    child = SubagentReference(agent_id=uuid4().hex, version=2, name="volatility-expert")
    main = ResolvedAgent(
        agent_id=uuid4().hex,
        name="risk-scene",
        version=3,
        system_prompt="调度风险分析",
        skill_refs=None,
        subagent_refs=[child],
    )

    config = await resolve_reference(
        AgentConfigRequest(agent_id=main.agent_id),
        user_id=uuid4().hex,
        resolver=Resolver(main),
    )

    assert config.subagents == [child]
