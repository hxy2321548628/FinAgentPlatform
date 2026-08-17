"""Skill 目录数据层的测试，连真 Postgres。"""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.preset.model import Visibility
from app.preset.skill import SkillRepository
from app.user.repository import User


@pytest.fixture
def skills(live_engine: AsyncEngine) -> SkillRepository:
    return SkillRepository(live_engine)


async def test_a_new_skill_comes_with_its_first_draft(skills: SkillRepository, owner: User) -> None:
    created = await skills.create(
        owner_id=owner.id,
        name=f"annualized-naming-{uuid4().hex[:8]}",
        subject="金融学",
        description="年化口径与产物命名约定",
        file_count=1,
        total_bytes=128,
    )

    assert created is not None
    detail = await skills.detail(created.id, owner_id=owner.id)
    assert detail is not None
    assert detail.skill.visibility is Visibility.PRIVATE
    assert [(one.version, one.status.value) for one in detail.versions] == [(1, "draft")]
    assert detail.versions[0].description == "年化口径与产物命名约定"


async def test_the_same_author_cannot_reuse_one_active_skill_name(skills: SkillRepository, owner: User) -> None:
    name = f"duplicate-{uuid4().hex[:8]}"
    first = await skills.create(
        owner_id=owner.id,
        name=name,
        subject="",
        description="a",
        file_count=1,
        total_bytes=1,
    )
    again = await skills.create(
        owner_id=owner.id,
        name=name,
        subject="",
        description="b",
        file_count=1,
        total_bytes=1,
    )

    assert first is not None
    assert again is None
