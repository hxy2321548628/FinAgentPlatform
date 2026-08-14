"""把提交配置中的 Skill 标识解析成冻结版本。"""

import logging
from typing import Protocol

from agent.config import AgentConfig, SkillReference
from preset.skill import ResolvedSkill

MAX_SKILLS_PER_RUN = 10

UNAVAILABLE_MESSAGE = "这个 Skill 现在用不了：可能作者已经收回共享、没有发布版本或删掉了它。请重新选择"
TOO_MANY_MESSAGE = f"一次运行最多挂 {MAX_SKILLS_PER_RUN} 个 Skill"

logger = logging.getLogger(__name__)


class SkillResolverProtocol(Protocol):
    """Skill 引用解析对目录层的全部要求。"""

    async def resolve(self, skill_id: str, *, user_id: str) -> ResolvedSkill | None:
        """按提交者身份解析一个可用 Skill。"""
        ...


class SkillReferenceError(ValueError):
    """Skill 引用无法形成一份可执行快照。"""


async def resolve_skill_references(
    config: AgentConfig,
    *,
    skill_ids: list[str] | None,
    user_id: str,
    resolver: SkillResolverProtocol,
) -> AgentConfig:
    """按提交者可见性把 Skill 标识解析成冻结版本。

    Args:
        config: 已解析 agent 引用的运行配置。
        skill_ids: 教师选择的 Skill 标识。
        user_id: 提交者标识。
        resolver: Skill 目录层。

    Returns:
        带 Skill 快照的运行配置。

    Raises:
        SkillReferenceError: 数量超限、引用不可用或名称撞车。
    """
    bundled = config.skills or []
    if not skill_ids:
        return config
    if len(skill_ids) > MAX_SKILLS_PER_RUN:
        raise SkillReferenceError(TOO_MANY_MESSAGE)

    resolved: list[ResolvedSkill] = []
    for skill_id in skill_ids:
        one = await resolver.resolve(skill_id, user_id=user_id)
        if one is None:
            logger.info("Skill 引用解析失败：skill_id=%s user_id=%s", skill_id, user_id)
            raise SkillReferenceError(UNAVAILABLE_MESSAGE)
        resolved.append(one)

    temporary = [SkillReference(skill_id=one.skill_id, version=one.version, name=one.name) for one in resolved]
    references = _unique_references([*bundled, *temporary])
    if len(references) > MAX_SKILLS_PER_RUN:
        raise SkillReferenceError(TOO_MANY_MESSAGE)

    duplicate = _duplicate_name(references)
    if duplicate is not None:
        raise SkillReferenceError(f"同一次运行不能挂两个同名 Skill：{duplicate}")

    return config.model_copy(update={"skills": references})


def _unique_references(references: list[SkillReference]) -> list[SkillReference]:
    """按冻结三元组取并集，并保持 Agent 自带引用在前。"""
    unique: list[SkillReference] = []
    seen: set[tuple[str, int, str]] = set()
    for reference in references:
        identity = (reference.skill_id, reference.version, reference.name)
        if identity not in seen:
            unique.append(reference)
            seen.add(identity)
    return unique


def _duplicate_name(skills: list[SkillReference]) -> str | None:
    """返回第一个重复名称，没有则为 None。"""
    seen: set[str] = set()
    for skill in skills:
        if skill.name in seen:
            return skill.name
        seen.add(skill.name)
    return None
