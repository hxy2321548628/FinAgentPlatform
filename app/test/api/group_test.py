"""课题组端点：浏览、名册、加人移人、申请与审批。

**这一族端点里最危险的是邀请码**：它是准入凭证，而浏览列表对所有登录用户开放 ——
一旦跟着列表发出去，任何人都能把自己塞进任何组。因此有一条用例专门在整份响应文本里
找它。

第二危险的是「谁能管这个组」。组主是 `groups.owner_id` 一列，不是角色 ——
因此每一个管理动作都要有一条「别人来打会怎样」的用例，而不是只验组主自己那条路。
"""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api.platform import Platform
from auth.password import PasswordHasher
from group.model import JoinRequestStatus
from group.repository import Group
from test.api.conftest import login, make_group, signup
from user.model import UserRole
from user.repository import User

GROUP_PATH = "/api/groups"


@pytest.fixture
def teacher(client: TestClient) -> dict[str, str]:
    """`client` 一开始登着的那个教师。"""
    body: dict[str, str] = client.get("/api/auth/me").json()
    return body


@pytest.fixture
def group(client: TestClient, platform: Platform, teacher: dict[str, str]) -> Group:
    """一个教师带的组。"""
    return make_group(client, platform, owner_id=teacher["id"])


@pytest.fixture
def student(client: TestClient, platform: Platform, hasher: PasswordHasher) -> User:
    """一个学生账号，**还没登录**。"""
    return signup(client, platform, hasher, name=f"学生-{uuid4().hex[:8]}", role=UserRole.STUDENT)


def as_student(client: TestClient, student: User) -> None:
    client.cookies.clear()
    login(client, student.name)


def test_browsing_lists_a_group_with_its_owner_and_size(
    client: TestClient, group: Group, teacher: dict[str, str]
) -> None:
    """学生凭这一页挑组，因此「谁带的、多少人」都得在。"""
    listed = {one["id"]: one for one in client.get(GROUP_PATH).json()}

    assert listed[group.id]["owner_name"] == teacher["name"]
    assert listed[group.id]["member_count"] == 1


def test_browsing_never_leaks_the_invite_code(client: TestClient, group: Group, student: User) -> None:
    """邀请码跟着这一页发出去，就等于任何人都能把自己塞进任何组。"""
    as_student(client, student)

    text = client.get(GROUP_PATH).text

    assert group.invite_code not in text


def test_browsing_requires_login(client: TestClient) -> None:
    client.cookies.clear()

    assert client.get(GROUP_PATH).status_code == 401


def test_my_groups_show_the_invite_code_to_the_owner(client: TestClient, group: Group) -> None:
    """教师得先看得到码，才发得出去。"""
    mine = {one["id"]: one for one in client.get(f"{GROUP_PATH}/mine").json()}

    assert mine[group.id]["is_owner"] is True
    assert mine[group.id]["invite_code"] == group.invite_code


def test_my_groups_hide_the_invite_code_from_a_plain_member(client: TestClient, group: Group, student: User) -> None:
    """组员不是组主。他手上有码的话，招人这件事就绕开教师了。"""
    client.post(f"{GROUP_PATH}/{group.id}/members", json={"name": student.name})
    as_student(client, student)

    mine = {one["id"]: one for one in client.get(f"{GROUP_PATH}/mine").json()}

    assert mine[group.id]["is_owner"] is False
    assert mine[group.id]["invite_code"] is None


def test_my_groups_leave_out_the_ones_i_am_not_in(client: TestClient, group: Group, student: User) -> None:
    as_student(client, student)

    assert client.get(f"{GROUP_PATH}/mine").json() == []


def test_the_owner_sees_the_roster(client: TestClient, group: Group, student: User) -> None:
    client.post(f"{GROUP_PATH}/{group.id}/members", json={"name": student.name})

    roster = client.get(f"{GROUP_PATH}/{group.id}/members").json()

    found = {one["name"]: one for one in roster}
    assert found[student.name]["role"] == UserRole.STUDENT.value


def test_a_stranger_cannot_see_the_roster(client: TestClient, group: Group, student: User) -> None:
    """名册是别人的资源，因此给 404 而不是 403 —— 后者等于确认了「你猜的这个组是我的」。"""
    as_student(client, student)

    assert client.get(f"{GROUP_PATH}/{group.id}/members").status_code == 404


def test_the_owner_can_add_a_student_by_name(client: TestClient, group: Group, student: User) -> None:
    """按用户名加人：教师手上有的是学生报的名字，不是 uuid。"""
    response = client.post(f"{GROUP_PATH}/{group.id}/members", json={"name": student.name})

    assert response.status_code == 200, response.text
    assert student.name in {one["name"] for one in client.get(f"{GROUP_PATH}/{group.id}/members").json()}


def test_adding_the_same_student_twice_is_not_an_error(client: TestClient, group: Group, student: User) -> None:
    """教师重复点「添加」是常事，第二次该无事发生。"""
    client.post(f"{GROUP_PATH}/{group.id}/members", json={"name": student.name})

    assert client.post(f"{GROUP_PATH}/{group.id}/members", json={"name": student.name}).status_code == 200
    assert len(client.get(f"{GROUP_PATH}/{group.id}/members").json()) == 2


def test_adding_an_unknown_name_is_a_404(client: TestClient, group: Group) -> None:
    response = client.post(f"{GROUP_PATH}/{group.id}/members", json={"name": f"没有这个人-{uuid4().hex[:8]}"})

    assert response.status_code == 404


def test_a_stranger_cannot_add_members(client: TestClient, group: Group, student: User) -> None:
    as_student(client, student)

    assert client.post(f"{GROUP_PATH}/{group.id}/members", json={"name": student.name}).status_code == 404


def test_the_owner_can_remove_a_member(client: TestClient, group: Group, student: User) -> None:
    client.post(f"{GROUP_PATH}/{group.id}/members", json={"name": student.name})

    assert client.delete(f"{GROUP_PATH}/{group.id}/members/{student.id}").status_code == 204

    assert student.name not in {one["name"] for one in client.get(f"{GROUP_PATH}/{group.id}/members").json()}


def test_the_owner_cannot_remove_themselves(client: TestClient, group: Group, teacher: dict[str, str]) -> None:
    """组主移出自己之后，这个组在「我的组」里就再也找不到了 —— 那条查询走的是成员表。"""
    response = client.delete(f"{GROUP_PATH}/{group.id}/members/{teacher['id']}")

    assert response.status_code == 422


def test_a_stranger_cannot_remove_members(client: TestClient, group: Group, student: User) -> None:
    client.post(f"{GROUP_PATH}/{group.id}/members", json={"name": student.name})
    as_student(client, student)

    assert client.delete(f"{GROUP_PATH}/{group.id}/members/{student.id}").status_code == 404


def test_a_student_can_apply_to_a_group(client: TestClient, group: Group, student: User) -> None:
    as_student(client, student)

    response = client.post(f"{GROUP_PATH}/{group.id}/requests")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == JoinRequestStatus.PENDING.value


def test_applying_twice_is_refused(client: TestClient, group: Group, student: User) -> None:
    as_student(client, student)
    client.post(f"{GROUP_PATH}/{group.id}/requests")

    assert client.post(f"{GROUP_PATH}/{group.id}/requests").status_code == 422


def test_applying_to_a_group_i_am_already_in_is_refused(client: TestClient, group: Group, student: User) -> None:
    client.post(f"{GROUP_PATH}/{group.id}/members", json={"name": student.name})
    as_student(client, student)

    assert client.post(f"{GROUP_PATH}/{group.id}/requests").status_code == 422


def test_applying_to_an_unknown_group_is_a_404(client: TestClient, student: User) -> None:
    as_student(client, student)

    assert client.post(f"{GROUP_PATH}/{uuid4().hex}/requests").status_code == 404


def test_my_requests_carry_the_group_name_and_status(client: TestClient, group: Group, student: User) -> None:
    """学生要知道「我申请的那个组批了没」，只给组 id 的话页面上没东西可显示。"""
    as_student(client, student)
    client.post(f"{GROUP_PATH}/{group.id}/requests")

    mine = client.get(f"{GROUP_PATH}/mine/requests").json()

    assert [(one["group_name"], one["status"]) for one in mine] == [(group.name, JoinRequestStatus.PENDING.value)]


def test_the_pending_list_shows_the_applicant_to_the_owner(
    client: TestClient, group: Group, student: User, teacher: dict[str, str]
) -> None:
    as_student(client, student)
    client.post(f"{GROUP_PATH}/{group.id}/requests")
    login(client, teacher["name"])

    pending = client.get(f"{GROUP_PATH}/{group.id}/requests").json()

    assert [one["user_name"] for one in pending] == [student.name]


def test_a_stranger_cannot_read_the_pending_list(client: TestClient, group: Group, student: User) -> None:
    as_student(client, student)

    assert client.get(f"{GROUP_PATH}/{group.id}/requests").status_code == 404


def test_approving_puts_the_student_on_the_roster(
    client: TestClient, group: Group, student: User, teacher: dict[str, str]
) -> None:
    as_student(client, student)
    request_id = client.post(f"{GROUP_PATH}/{group.id}/requests").json()["id"]
    login(client, teacher["name"])

    response = client.post(f"{GROUP_PATH}/{group.id}/requests/{request_id}", json={"approved": True})

    assert response.status_code == 204, response.text
    assert student.name in {one["name"] for one in client.get(f"{GROUP_PATH}/{group.id}/members").json()}


def test_rejecting_keeps_the_student_out(
    client: TestClient, group: Group, student: User, teacher: dict[str, str]
) -> None:
    as_student(client, student)
    request_id = client.post(f"{GROUP_PATH}/{group.id}/requests").json()["id"]
    login(client, teacher["name"])

    response = client.post(f"{GROUP_PATH}/{group.id}/requests/{request_id}", json={"approved": False})

    assert response.status_code == 204, response.text
    assert student.name not in {one["name"] for one in client.get(f"{GROUP_PATH}/{group.id}/members").json()}


def test_deciding_twice_is_refused(client: TestClient, group: Group, student: User, teacher: dict[str, str]) -> None:
    """两个标签页各点一次，第二次该是「已经处理过了」而不是把否决改成批准。"""
    as_student(client, student)
    request_id = client.post(f"{GROUP_PATH}/{group.id}/requests").json()["id"]
    login(client, teacher["name"])
    client.post(f"{GROUP_PATH}/{group.id}/requests/{request_id}", json={"approved": False})

    response = client.post(f"{GROUP_PATH}/{group.id}/requests/{request_id}", json={"approved": True})

    assert response.status_code == 422


def test_a_stranger_cannot_decide(client: TestClient, group: Group, student: User, teacher: dict[str, str]) -> None:
    as_student(client, student)
    request_id = client.post(f"{GROUP_PATH}/{group.id}/requests").json()["id"]

    response = client.post(f"{GROUP_PATH}/{group.id}/requests/{request_id}", json={"approved": True})

    assert response.status_code == 404


def test_a_request_from_another_group_cannot_be_decided_here(
    client: TestClient, platform: Platform, group: Group, student: User, teacher: dict[str, str]
) -> None:
    """审批路径上带着组 id，它必须真的被核对 —— 否则组主能批别人组里的申请。"""
    other = make_group(client, platform, owner_id=teacher["id"])
    as_student(client, student)
    request_id = client.post(f"{GROUP_PATH}/{other.id}/requests").json()["id"]
    login(client, teacher["name"])

    response = client.post(f"{GROUP_PATH}/{group.id}/requests/{request_id}", json={"approved": True})

    assert response.status_code == 404
