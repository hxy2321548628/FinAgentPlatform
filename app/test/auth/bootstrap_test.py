"""首个管理员初始化的测试，连真 Postgres。

**核心是「只在空库时建」**（步骤一验证⑥）：否则运维改过管理员口令之后，
一次重启就把它改回 `.env` 里那个，而这种回退不报错。
"""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from auth.bootstrap import ensure_first_admin
from auth.password import PasswordHasher
from test.conftest import json_log
from user.model import UserRole
from user.repository import UserRepository

ADMIN_PASSWORD = "口令-admin"


@pytest.fixture
def hasher() -> PasswordHasher:
    return PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)


@pytest.fixture
def repository(live_engine: AsyncEngine) -> UserRepository:
    return UserRepository(live_engine)


class EmptyUserRepository(UserRepository):
    """计数恒为 0 的仓储。

    测试库是全套用例共用的，里面早就有别的账号，真正的空库造不出来。只把计数摆成 0，
    其余读写仍然打在真库上 —— 建号那一步因此是真的。
    """

    async def count(self) -> int:
        return 0


@pytest.fixture
def empty(live_engine: AsyncEngine) -> UserRepository:
    return EmptyUserRepository(live_engine)


async def test_an_empty_database_gets_its_first_admin(
    repository: UserRepository, empty: UserRepository, hasher: PasswordHasher
) -> None:
    name = f"admin-{uuid4().hex[:8]}"

    created = await ensure_first_admin(repository=empty, hasher=hasher, name=name, password=ADMIN_PASSWORD)

    assert created is True
    credential = await repository.find_by_name(name)
    assert credential is not None
    assert credential.user.role is UserRole.ADMIN
    assert hasher.verify(credential.password_hash, ADMIN_PASSWORD) is True


async def test_a_populated_database_is_left_alone(repository: UserRepository, hasher: PasswordHasher) -> None:
    """已经有人了就一个字都不改 —— 这一条是「重启不覆盖已改过的口令」的全部内容。"""
    name = f"admin-{uuid4().hex[:8]}"
    await repository.create(name=name, password_hash=hasher.hash("运维后来改的口令"), role=UserRole.ADMIN)

    created = await ensure_first_admin(repository=repository, hasher=hasher, name=name, password=ADMIN_PASSWORD)

    assert created is False
    credential = await repository.find_by_name(name)
    assert credential is not None
    assert hasher.verify(credential.password_hash, "运维后来改的口令") is True
    assert hasher.verify(credential.password_hash, ADMIN_PASSWORD) is False


async def test_an_empty_database_without_configuration_warns_loudly(
    empty: UserRepository, hasher: PasswordHasher
) -> None:
    """空库又没配管理员 = 谁都登不进来。它不该是一条静默的分支。"""
    with json_log("auth.bootstrap") as recorded:
        created = await ensure_first_admin(repository=empty, hasher=hasher, name="", password="")

    assert created is False
    assert any(line["level"] == "WARNING" for line in recorded)


async def test_a_second_process_starting_at_the_same_time_does_not_fail(
    empty: UserRepository, hasher: PasswordHasher
) -> None:
    """两个副本同时启动会同时读到 0。撞车的那一方按「已经有人建好了」处理，不是失败。"""
    name = f"admin-{uuid4().hex[:8]}"

    first = await ensure_first_admin(repository=empty, hasher=hasher, name=name, password=ADMIN_PASSWORD)
    second = await ensure_first_admin(repository=empty, hasher=hasher, name=name, password=ADMIN_PASSWORD)

    assert first is True
    assert second is False
