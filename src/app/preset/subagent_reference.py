"""把提交配置中的子智能体标识解析成冻结版本。"""

import logging
from typing import Protocol

from app.agent.config import AgentConfig, SubagentReference
from app.agent.subagent import MAX_SUBAGENT
from app.preset.repository import ResolvedAgent

UNAVAILABLE_MESSAGE = "这个子智能体现在用不了：可能作者已经收回共享、没有发布版本或删掉了它。请重新选择"
NESTED_MESSAGE = "已挂子智能体的场景不能再作为子智能体"
TOO_MANY_MESSAGE = f"一次运行最多挂 {MAX_SUBAGENT} 个子智能体"

logger = logging.getLogger(__name__)


class SubagentResolverProtocol(Protocol):
    """子智能体引用解析对目录层的全部要求。"""

    async def resolve(self, agent_id: str, *, user_id: str) -> ResolvedAgent | None:
        """按提交者身份解析一个可用智能体。"""
        ...


class SubagentReferenceError(ValueError):
    """子智能体引用无法形成一份可执行快照。"""


async def resolve_subagent_references(
    config: AgentConfig,
    *,
    subagent_ids: list[str] | None,
    user_id: str,
    resolver: SubagentResolverProtocol,
) -> AgentConfig:
    """解析本轮临时子智能体，并与主智能体自带引用取并集。"""
    bundled = config.subagents
    if not subagent_ids:
        return config
    if len(subagent_ids) > MAX_SUBAGENT:
        raise SubagentReferenceError(TOO_MANY_MESSAGE)

    resolved: list[ResolvedAgent] = []
    for agent_id in subagent_ids:
        one = await resolver.resolve(agent_id, user_id=user_id)
        if one is None:
            logger.info("子智能体引用解析失败：agent_id=%s user_id=%s", agent_id, user_id)
            raise SubagentReferenceError(UNAVAILABLE_MESSAGE)
        if one.subagent_refs:
            raise SubagentReferenceError(NESTED_MESSAGE)
        resolved.append(one)

    temporary = [SubagentReference(agent_id=one.agent_id, version=one.version, name=one.name) for one in resolved]
    references = _unique_references([*bundled, *temporary])
    if len(references) > MAX_SUBAGENT:
        raise SubagentReferenceError(TOO_MANY_MESSAGE)

    duplicate = _duplicate_name(references)
    if duplicate is not None:
        raise SubagentReferenceError(f"同一次运行不能挂两个同名子智能体：{duplicate}")

    return config.model_copy(update={"subagents": references})


def _unique_references(references: list[SubagentReference]) -> list[SubagentReference]:
    """按冻结三元组取并集，并保持主智能体自带引用在前。"""
    unique: list[SubagentReference] = []
    seen: set[tuple[str, int, str]] = set()
    for reference in references:
        identity = (reference.agent_id, reference.version, reference.name)
        if identity not in seen:
            unique.append(reference)
            seen.add(identity)
    return unique


def _duplicate_name(subagents: list[SubagentReference]) -> str | None:
    """返回第一个重复名称，没有则为 None。"""
    seen: set[str] = set()
    for subagent in subagents:
        if subagent.name in seen:
            return subagent.name
        seen.add(subagent.name)
    return None
