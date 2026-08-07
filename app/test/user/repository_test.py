"""`users` 表读写的测试，连真 Postgres。"""

from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from user.model import UserRole
from user.repository import UserRepository

HASH = "$argon2id$假的但形状对"


@pytest.fixture
def repository(live_engine: AsyncEngine) -> UserRepository:
    return UserRepository(live_engine)


def _name() -> str:
    return f"teacher-{uuid4().hex[:8]}"


async def test_a_created_user_is_found_by_name(repository: UserRepository) -> None:
    name = _name()
    created = await repository.create(name=name, password_hash=HASH, role=UserRole.TEACHER)

    found = await repository.find_by_name(name)

    assert found is not None
    assert found.user == created
    assert found.password_hash == HASH


async def test_a_new_user_is_active_and_has_no_quota_override(repository: UserRepository) -> None:
    """配额两项留空表示「跟着角色的默认档走」—— 建号时不把默认值抄进行里。"""
    created = await repository.create(name=_name(), password_hash=HASH, role=UserRole.STUDENT)

    assert created.is_active is True
    assert created.quota_tokens_daily is None
    assert created.quota_concurrent_runs is None


async def test_an_unknown_name_finds_nothing(repository: UserRepository) -> None:
    assert await repository.find_by_name(f"没有这个人-{uuid4().hex}") is None


async def test_the_same_name_cannot_be_taken_twice(repository: UserRepository) -> None:
    name = _name()
    await repository.create(name=name, password_hash=HASH, role=UserRole.TEACHER)

    with pytest.raises(IntegrityError):
        await repository.create(name=name, password_hash=HASH, role=UserRole.STUDENT)


async def test_a_user_is_found_by_id(repository: UserRepository) -> None:
    created = await repository.create(name=_name(), password_hash=HASH, role=UserRole.ADMIN)

    assert await repository.get(created.id) == created


async def test_a_malformed_id_finds_nothing_instead_of_raising(repository: UserRepository) -> None:
    """用户 id 来自 session 与 URL，属于不可信输入 —— 解析不了就是「查不到」，不是 500。"""
    assert await repository.get("这不是一个 uuid") is None


async def test_counting_sees_the_rows_that_were_written(repository: UserRepository) -> None:
    """首个管理员的初始化只看它是不是 0，因此它必须真的数得对。"""
    before = await repository.count()

    await repository.create(name=_name(), password_hash=HASH, role=UserRole.TEACHER)

    assert await repository.count() == before + 1
