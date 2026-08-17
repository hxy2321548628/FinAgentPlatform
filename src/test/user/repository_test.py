"""`users` 表读写的测试，连真 Postgres。"""

from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.user.model import UserRole
from app.user.repository import UserRepository

HASH = "$argon2id$假的但形状对"


@pytest.fixture
def repository(live_engine: AsyncEngine) -> UserRepository:
    return UserRepository(live_engine)


def _name() -> str:
    return f"teacher-{uuid4().hex[:8]}"


def _email() -> str:
    return f"{uuid4().hex[:8]}@zuel.edu.cn"


async def test_a_user_is_found_by_email(repository: UserRepository) -> None:
    """**登录得认邮箱**：教师记得住自己的邮箱，未必记得住当初注册的用户名。"""
    email = _email()
    created = await repository.create(name=_name(), password_hash=HASH, role=UserRole.TEACHER, email=email)

    found = await repository.find_by_identifier(email)

    assert found is not None
    assert found.user == created


async def test_a_user_is_still_found_by_name(repository: UserRepository) -> None:
    """**同一个入口两种写法都得认** —— 只认邮箱的话，改完登录框老用户就进不来了。"""
    name = _name()
    created = await repository.create(name=name, password_hash=HASH, role=UserRole.TEACHER, email=_email())

    found = await repository.find_by_identifier(name)

    assert found is not None
    assert found.user == created


async def test_the_same_email_cannot_be_taken_twice(repository: UserRepository) -> None:
    """邮箱是登录凭据，重了就分不清进来的是谁。"""
    email = _email()
    await repository.create(name=_name(), password_hash=HASH, role=UserRole.TEACHER, email=email)

    with pytest.raises(IntegrityError):
        await repository.create(name=_name(), password_hash=HASH, role=UserRole.STUDENT, email=email)


async def test_an_unknown_identifier_finds_nothing(repository: UserRepository) -> None:
    assert await repository.find_by_identifier(f"没有这个人-{uuid4().hex}") is None


async def test_a_created_user_is_found_by_name(repository: UserRepository) -> None:
    name = _name()
    created = await repository.create(name=name, password_hash=HASH, role=UserRole.TEACHER, email=_email())

    found = await repository.find_by_name(name)

    assert found is not None
    assert found.user == created
    assert found.password_hash == HASH


async def test_a_new_user_is_active_and_has_no_quota_override(repository: UserRepository) -> None:
    """配额两项留空表示「跟着角色的默认档走」—— 建号时不把默认值抄进行里。"""
    created = await repository.create(name=_name(), password_hash=HASH, role=UserRole.STUDENT, email=_email())

    assert created.is_active is True
    assert created.quota_tokens_daily is None
    assert created.quota_concurrent_runs is None


async def test_an_unknown_name_finds_nothing(repository: UserRepository) -> None:
    assert await repository.find_by_name(f"没有这个人-{uuid4().hex}") is None


async def test_the_same_name_cannot_be_taken_twice(repository: UserRepository) -> None:
    name = _name()
    await repository.create(name=name, password_hash=HASH, role=UserRole.TEACHER, email=_email())

    with pytest.raises(IntegrityError):
        await repository.create(name=name, password_hash=HASH, role=UserRole.STUDENT, email=_email())


async def test_a_user_is_found_by_id(repository: UserRepository) -> None:
    created = await repository.create(name=_name(), password_hash=HASH, role=UserRole.ADMIN, email=_email())

    assert await repository.get(created.id) == created


async def test_a_malformed_id_finds_nothing_instead_of_raising(repository: UserRepository) -> None:
    """用户 id 来自 session 与 URL，属于不可信输入 —— 解析不了就是「查不到」，不是 500。"""
    assert await repository.get("这不是一个 uuid") is None


async def test_a_user_can_be_created_inactive(repository: UserRepository) -> None:
    """没填邀请码的注册建出来就是停用的，登不上，等管理员点一下。"""
    created = await repository.create(
        name=_name(), password_hash=HASH, role=UserRole.STUDENT, is_active=False, email=_email()
    )

    assert created.is_active is False


async def test_listing_sees_a_freshly_created_account(repository: UserRepository) -> None:
    created = await repository.create(name=_name(), password_hash=HASH, role=UserRole.TEACHER, email=_email())

    assert created.id in {one.id for one in await repository.list_all()}


async def test_the_newest_account_is_listed_first(repository: UserRepository) -> None:
    """管理员这一页的头等大事是「谁在等激活」，而那永远是最近注册的那几个。"""
    created = await repository.create(
        name=_name(), password_hash=HASH, role=UserRole.STUDENT, is_active=False, email=_email()
    )

    listed = await repository.list_all()

    assert listed[0].id == created.id


async def test_activating_a_user_flips_the_flag(repository: UserRepository) -> None:
    created = await repository.create(
        name=_name(), password_hash=HASH, role=UserRole.STUDENT, is_active=False, email=_email()
    )

    assert await repository.set_active(created.id, is_active=True) is True

    found = await repository.get(created.id)
    assert found is not None
    assert found.is_active is True


async def test_activating_an_unknown_user_changes_nothing(repository: UserRepository) -> None:
    assert await repository.set_active(uuid4().hex, is_active=True) is False


async def test_a_quota_override_is_written(repository: UserRepository) -> None:
    """管理员给某个人单独调配额，写进去的就是闸门要读的那一列。"""
    created = await repository.create(name=_name(), password_hash=HASH, role=UserRole.STUDENT, email=_email())

    assert await repository.update_profile(created.id, quota_tokens_daily=1234, quota_concurrent_runs=2) is True

    found = await repository.get(created.id)
    assert found is not None
    assert found.quota_tokens_daily == 1234
    assert found.quota_concurrent_runs == 2


async def test_clearing_a_quota_override_returns_to_the_role_default(repository: UserRepository) -> None:
    """**清空要能清得掉。**

    留空表示「跟着角色的默认档走」，因此把它改回 None 是一个有意义的操作 ——
    若实现把 None 当成「这个字段不用改」，调过配额的人就再也回不到默认档了。
    """
    created = await repository.create(name=_name(), password_hash=HASH, role=UserRole.TEACHER, email=_email())
    await repository.update_profile(created.id, quota_tokens_daily=999)

    await repository.update_profile(created.id, quota_tokens_daily=None)

    found = await repository.get(created.id)
    assert found is not None
    assert found.quota_tokens_daily is None


async def test_a_role_can_be_changed(repository: UserRepository) -> None:
    created = await repository.create(name=_name(), password_hash=HASH, role=UserRole.STUDENT, email=_email())

    assert await repository.update_profile(created.id, role=UserRole.TEACHER) is True

    found = await repository.get(created.id)
    assert found is not None
    assert found.role is UserRole.TEACHER


async def test_updating_an_unknown_user_changes_nothing(repository: UserRepository) -> None:
    assert await repository.update_profile(uuid4().hex, role=UserRole.ADMIN) is False


async def test_counting_sees_the_rows_that_were_written(repository: UserRepository) -> None:
    """首个管理员的初始化只看它是不是 0，因此它必须真的数得对。"""
    before = await repository.count()

    await repository.create(name=_name(), password_hash=HASH, role=UserRole.TEACHER, email=_email())

    assert await repository.count() == before + 1
