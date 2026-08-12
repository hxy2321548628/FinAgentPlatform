"""组与入组申请读写的测试，连真 Postgres。"""

from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from group.model import INVITE_CODE_LENGTH, JoinRequestStatus
from group.repository import GroupRepository, JoinRequestRepository
from test.conftest import FAKE_HASH
from user.model import UserRole
from user.repository import User, UserRepository


@pytest.fixture
def groups(live_engine: AsyncEngine) -> GroupRepository:
    return GroupRepository(live_engine)


@pytest.fixture
def requests(live_engine: AsyncEngine) -> JoinRequestRepository:
    return JoinRequestRepository(live_engine)


@pytest.fixture
def users(live_engine: AsyncEngine) -> UserRepository:
    return UserRepository(live_engine)


async def _student(users: UserRepository) -> User:
    return await users.create(name=f"student-{uuid4().hex[:8]}", password_hash=FAKE_HASH, role=UserRole.STUDENT)


def _group_name() -> str:
    return f"课题组-{uuid4().hex[:8]}"


async def test_a_created_group_carries_an_invite_code(groups: GroupRepository, owner: User) -> None:
    created = await groups.create(name=_group_name(), owner_id=owner.id)

    assert len(created.invite_code) == INVITE_CODE_LENGTH
    assert created.owner_id == owner.id


async def test_two_groups_do_not_share_an_invite_code(groups: GroupRepository, owner: User) -> None:
    """撞码等于把学生发进别人的组。"""
    first = await groups.create(name=_group_name(), owner_id=owner.id)
    second = await groups.create(name=_group_name(), owner_id=owner.id)

    assert first.invite_code != second.invite_code


async def test_the_owner_is_on_the_roster_from_the_start(groups: GroupRepository, owner: User) -> None:
    """组主不在自己的名册里的话，「我的组」就查不到它 —— 那条查询走的正是成员表。"""
    created = await groups.create(name=_group_name(), owner_id=owner.id)

    assert await groups.is_member(group_id=created.id, user_id=owner.id) is True


async def test_a_group_is_found_by_its_invite_code(groups: GroupRepository, owner: User) -> None:
    created = await groups.create(name=_group_name(), owner_id=owner.id)

    assert await groups.find_by_invite_code(created.invite_code) == created


async def test_an_unknown_invite_code_finds_nothing(groups: GroupRepository) -> None:
    assert await groups.find_by_invite_code("NOSUCH99") is None


async def test_the_same_group_name_cannot_be_taken_twice(groups: GroupRepository, owner: User) -> None:
    """重名会让学生在浏览列表里没法分辨该申请哪一个。"""
    name = _group_name()
    await groups.create(name=name, owner_id=owner.id)

    with pytest.raises(IntegrityError):
        await groups.create(name=name, owner_id=owner.id)


async def test_adding_the_same_member_twice_is_not_an_error(
    groups: GroupRepository, users: UserRepository, owner: User
) -> None:
    """教师重复点「添加」是常事，第二次该无事发生而不是 500。"""
    created = await groups.create(name=_group_name(), owner_id=owner.id)
    student = await _student(users)

    assert await groups.add_member(group_id=created.id, user_id=student.id) is True
    assert await groups.add_member(group_id=created.id, user_id=student.id) is False
    assert len(await groups.list_member(created.id)) == 2


async def test_a_removed_member_is_gone_from_the_roster(
    groups: GroupRepository, users: UserRepository, owner: User
) -> None:
    created = await groups.create(name=_group_name(), owner_id=owner.id)
    student = await _student(users)
    await groups.add_member(group_id=created.id, user_id=student.id)

    await groups.remove_member(group_id=created.id, user_id=student.id)

    assert await groups.is_member(group_id=created.id, user_id=student.id) is False


async def test_the_roster_carries_names_and_roles(groups: GroupRepository, users: UserRepository, owner: User) -> None:
    """名册要给人看，光有 uuid 教师认不出谁是谁。"""
    created = await groups.create(name=_group_name(), owner_id=owner.id)
    student = await _student(users)
    await groups.add_member(group_id=created.id, user_id=student.id)

    roster = await groups.list_member(created.id)

    found = {one.user_id: one for one in roster}
    assert found[student.id].name == student.name
    assert found[student.id].role is UserRole.STUDENT


async def test_browsing_shows_the_owner_name_and_the_head_count(
    groups: GroupRepository, users: UserRepository, owner: User
) -> None:
    """学生凭这一页挑组，因此「谁带的、多少人」必须在里面。"""
    created = await groups.create(name=_group_name(), owner_id=owner.id)
    await groups.add_member(group_id=created.id, user_id=(await _student(users)).id)

    summary = {one.id: one for one in await groups.list_all()}

    assert summary[created.id].owner_name == owner.name
    assert summary[created.id].member_count == 2


async def test_my_groups_are_only_the_ones_i_belong_to(
    groups: GroupRepository, users: UserRepository, owner: User
) -> None:
    mine = await groups.create(name=_group_name(), owner_id=owner.id)
    await groups.create(name=_group_name(), owner_id=owner.id)
    student = await _student(users)
    await groups.add_member(group_id=mine.id, user_id=student.id)

    assert [one.id for one in await groups.list_for_user(student.id)] == [mine.id]


async def test_a_created_request_is_pending(
    groups: GroupRepository, requests: JoinRequestRepository, users: UserRepository, owner: User
) -> None:
    created = await groups.create(name=_group_name(), owner_id=owner.id)
    student = await _student(users)

    applied = await requests.create(group_id=created.id, user_id=student.id)

    assert applied is not None
    assert applied.status is JoinRequestStatus.PENDING


async def test_a_second_request_while_one_is_pending_is_refused(
    groups: GroupRepository, requests: JoinRequestRepository, users: UserRepository, owner: User
) -> None:
    """连点两次只该留下一条待办，否则教师的审批列表里全是同一个人。"""
    created = await groups.create(name=_group_name(), owner_id=owner.id)
    student = await _student(users)
    await requests.create(group_id=created.id, user_id=student.id)

    assert await requests.create(group_id=created.id, user_id=student.id) is None


async def test_approving_puts_the_applicant_on_the_roster(
    groups: GroupRepository, requests: JoinRequestRepository, users: UserRepository, owner: User
) -> None:
    """批准与入组是同一件事。分成两步的话中间失败会留下「批了却没进组」。"""
    created = await groups.create(name=_group_name(), owner_id=owner.id)
    student = await _student(users)
    applied = await requests.create(group_id=created.id, user_id=student.id)
    assert applied is not None

    assert await requests.decide(applied.id, approved=True) is True

    assert await groups.is_member(group_id=created.id, user_id=student.id) is True


async def test_rejecting_leaves_the_roster_alone(
    groups: GroupRepository, requests: JoinRequestRepository, users: UserRepository, owner: User
) -> None:
    created = await groups.create(name=_group_name(), owner_id=owner.id)
    student = await _student(users)
    applied = await requests.create(group_id=created.id, user_id=student.id)
    assert applied is not None

    assert await requests.decide(applied.id, approved=False) is True

    assert await groups.is_member(group_id=created.id, user_id=student.id) is False


async def test_a_rejected_applicant_can_apply_again(
    groups: GroupRepository, requests: JoinRequestRepository, users: UserRepository, owner: User
) -> None:
    """一次否决不该是永久拉黑 —— 条件唯一索引只盖 pending 那一段。"""
    created = await groups.create(name=_group_name(), owner_id=owner.id)
    student = await _student(users)
    applied = await requests.create(group_id=created.id, user_id=student.id)
    assert applied is not None
    await requests.decide(applied.id, approved=False)

    assert await requests.create(group_id=created.id, user_id=student.id) is not None


async def test_deciding_an_already_decided_request_changes_nothing(
    groups: GroupRepository, requests: JoinRequestRepository, users: UserRepository, owner: User
) -> None:
    """两个浏览器标签页各点一次，第二次该是「已经处理过了」而不是把否决改成批准。"""
    created = await groups.create(name=_group_name(), owner_id=owner.id)
    student = await _student(users)
    applied = await requests.create(group_id=created.id, user_id=student.id)
    assert applied is not None
    await requests.decide(applied.id, approved=False)

    assert await requests.decide(applied.id, approved=True) is False

    assert await groups.is_member(group_id=created.id, user_id=student.id) is False


async def test_the_pending_list_carries_the_applicant_name(
    groups: GroupRepository, requests: JoinRequestRepository, users: UserRepository, owner: User
) -> None:
    created = await groups.create(name=_group_name(), owner_id=owner.id)
    student = await _student(users)
    await requests.create(group_id=created.id, user_id=student.id)

    pending = await requests.list_pending(created.id)

    assert [one.user_name for one in pending] == [student.name]


async def test_the_pending_list_leaves_out_the_decided_ones(
    groups: GroupRepository, requests: JoinRequestRepository, users: UserRepository, owner: User
) -> None:
    created = await groups.create(name=_group_name(), owner_id=owner.id)
    student = await _student(users)
    applied = await requests.create(group_id=created.id, user_id=student.id)
    assert applied is not None
    await requests.decide(applied.id, approved=True)

    assert await requests.list_pending(created.id) == []


async def test_my_requests_carry_the_group_name(
    groups: GroupRepository, requests: JoinRequestRepository, users: UserRepository, owner: User
) -> None:
    """学生要知道「我申请的那个组批了没」，只给组 id 的话页面上没东西可显示。"""
    created = await groups.create(name=_group_name(), owner_id=owner.id)
    student = await _student(users)
    await requests.create(group_id=created.id, user_id=student.id)

    mine = await requests.list_for_user(student.id)

    assert [(one.group_name, one.status) for one in mine] == [(created.name, JoinRequestStatus.PENDING)]


async def test_a_malformed_id_finds_nothing_instead_of_raising(groups: GroupRepository) -> None:
    """组 id 来自 URL，属于不可信输入 —— 解析不了就是「查不到」，不是 500。"""
    assert await groups.get("这不是一个 uuid") is None
    assert await groups.list_for_user("这也不是") == []
