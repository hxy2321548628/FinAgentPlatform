"""Agent 自带 Skill 与本轮 Skill 的合并规则。"""

from uuid import uuid4

import pytest

from app.agent.config import AgentConfig, SkillReference
from app.preset.skill import ResolvedSkill
from app.preset.skill_reference import SkillReferenceError, resolve_skill_references


class Resolver:
    """按标识返回预置 Skill 的窄测试替身。"""

    def __init__(self, skills: dict[str, ResolvedSkill]) -> None:
        self._skills = skills

    async def resolve(self, skill_id: str, *, user_id: str) -> ResolvedSkill | None:
        return self._skills.get(skill_id)


def resolved(name: str) -> ResolvedSkill:
    """建立一个已发布 Skill 引用。"""
    return ResolvedSkill(skill_id=uuid4().hex, name=name, version=1)


async def test_agent_and_run_skill_references_are_merged() -> None:
    bundled = resolved("annualized-252")
    temporary = resolved("event-window")
    config = AgentConfig(skills=[SkillReference(skill_id=bundled.skill_id, version=bundled.version, name=bundled.name)])

    merged = await resolve_skill_references(
        config,
        skill_ids=[temporary.skill_id],
        user_id=uuid4().hex,
        resolver=Resolver({temporary.skill_id: temporary}),
    )

    assert merged.skills == [
        SkillReference(skill_id=bundled.skill_id, version=1, name="annualized-252"),
        SkillReference(skill_id=temporary.skill_id, version=1, name="event-window"),
    ]


async def test_the_same_frozen_reference_is_only_kept_once() -> None:
    skill = resolved("annualized-252")
    reference = SkillReference(skill_id=skill.skill_id, version=skill.version, name=skill.name)

    merged = await resolve_skill_references(
        AgentConfig(skills=[reference]),
        skill_ids=[skill.skill_id],
        user_id=uuid4().hex,
        resolver=Resolver({skill.skill_id: skill}),
    )

    assert merged.skills == [reference]


async def test_an_agent_skill_and_a_temporary_skill_with_the_same_name_are_rejected() -> None:
    bundled = resolved("annualized-252")
    temporary = resolved("annualized-252")
    config = AgentConfig(skills=[SkillReference(skill_id=bundled.skill_id, version=bundled.version, name=bundled.name)])

    with pytest.raises(SkillReferenceError, match="同名 Skill"):
        await resolve_skill_references(
            config,
            skill_ids=[temporary.skill_id],
            user_id=uuid4().hex,
            resolver=Resolver({temporary.skill_id: temporary}),
        )


async def test_the_combined_skill_set_cannot_exceed_ten() -> None:
    bundled = resolved("bundled")
    temporary = [resolved(f"temporary-{index}") for index in range(10)]
    config = AgentConfig(skills=[SkillReference(skill_id=bundled.skill_id, version=bundled.version, name=bundled.name)])

    with pytest.raises(SkillReferenceError, match="最多挂 10 个"):
        await resolve_skill_references(
            config,
            skill_ids=[one.skill_id for one in temporary],
            user_id=uuid4().hex,
            resolver=Resolver({one.skill_id: one for one in temporary}),
        )
