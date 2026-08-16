"""管理员对账号与组的管理：建号、列号、启停，以及建组。

这是**教师账号唯一的来源** —— 自助注册出来的一律是学生。首个管理员由 `.env` 在空库时
建一次，其余所有账号从这里来。
"""

from uuid import uuid4

from fastapi.testclient import TestClient

from api.schema import MIN_PASSWORD_LENGTH
from test.api.conftest import TEST_PASSWORD, as_admin
from user.model import UserRole

USER_PATH = "/api/admin/users"
GROUP_PATH = "/api/admin/groups"
REGISTER_PATH = "/api/auth/register"

NEW_PASSWORD = "口令-account"


def _email() -> str:
    return f"{uuid4().hex[:8]}@zuel.edu.cn"


def _name(prefix: str = "新账号") -> str:
    return f"{prefix}-{uuid4().hex[:8]}"


def _me(client: TestClient) -> dict[str, str]:
    body: dict[str, str] = client.get("/api/auth/me").json()
    return body


def test_an_admin_can_create_a_teacher(client: TestClient, admin: str) -> None:
    as_admin(client, admin)

    response = client.post(
        USER_PATH, json={"name": _name("教师"), "email": _email(), "password": NEW_PASSWORD, "role": "teacher"}
    )

    assert response.status_code == 200, response.text
    assert response.json()["role"] == UserRole.TEACHER.value
    assert response.json()["is_active"] is True


def test_the_created_account_can_log_in(client: TestClient, admin: str) -> None:
    """建出来登不上的话，这个端点等于什么都没做。"""
    as_admin(client, admin)
    name = _name("教师")
    client.post(USER_PATH, json={"name": name, "email": _email(), "password": NEW_PASSWORD, "role": "teacher"})

    client.cookies.clear()
    assert client.post("/api/auth/login", json={"name": name, "password": NEW_PASSWORD}).status_code == 200


def test_a_teacher_cannot_create_accounts(client: TestClient) -> None:
    """建号是管理能力。教师能建号的话，配额分档立刻就绕开了。"""
    response = client.post(
        USER_PATH, json={"name": _name(), "email": _email(), "password": NEW_PASSWORD, "role": "teacher"}
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_an_anonymous_visitor_cannot_create_accounts(client: TestClient) -> None:
    client.cookies.clear()

    response = client.post(
        USER_PATH, json={"name": _name(), "email": _email(), "password": NEW_PASSWORD, "role": "teacher"}
    )

    assert response.status_code == 401


def test_a_taken_name_is_refused(client: TestClient, admin: str) -> None:
    as_admin(client, admin)
    name = _name()
    client.post(USER_PATH, json={"name": name, "email": _email(), "password": NEW_PASSWORD, "role": "student"})

    response = client.post(
        USER_PATH, json={"name": name, "email": _email(), "password": NEW_PASSWORD, "role": "student"}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_a_short_password_is_refused(client: TestClient, admin: str) -> None:
    as_admin(client, admin)

    response = client.post(
        USER_PATH, json={"name": _name(), "password": "x" * (MIN_PASSWORD_LENGTH - 1), "role": "teacher"}
    )

    assert response.status_code == 422


def test_listing_shows_the_accounts_waiting_for_activation(client: TestClient, admin: str) -> None:
    """管理员打开这一页多半就是为了处理这些人，所以它们必须在里面看得见。"""
    name = _name("待激活")
    client.post(REGISTER_PATH, json={"name": name, "email": _email(), "password": NEW_PASSWORD})
    as_admin(client, admin)

    listed = client.get(USER_PATH).json()

    waiting = [one for one in listed if one["name"] == name]
    assert waiting
    assert waiting[0]["is_active"] is False


def test_the_listing_never_carries_a_password_hash(client: TestClient, admin: str) -> None:
    """哈希只在登录那一条路径上用得着。它出现在任何响应里都是纯粹的风险。"""
    as_admin(client, admin)

    text = client.get(USER_PATH).text

    assert "argon2" not in text
    assert "password" not in text


def test_a_teacher_cannot_list_accounts(client: TestClient) -> None:
    assert client.get(USER_PATH).status_code == 403


def test_activating_lets_the_waiting_student_log_in(client: TestClient, admin: str) -> None:
    """无码注册这条路的另一半：管理员点一下，人就进来了。"""
    name = _name("待激活")
    created = client.post(REGISTER_PATH, json={"name": name, "email": _email(), "password": NEW_PASSWORD}).json()
    as_admin(client, admin)

    response = client.patch(f"{USER_PATH}/{created['id']}", json={"is_active": True})

    assert response.status_code == 200, response.text
    client.cookies.clear()
    assert client.post("/api/auth/login", json={"name": name, "password": NEW_PASSWORD}).status_code == 200


def test_deactivating_shuts_an_account_out(client: TestClient, admin: str) -> None:
    teacher = _me(client)
    as_admin(client, admin)

    assert client.patch(f"{USER_PATH}/{teacher['id']}", json={"is_active": False}).status_code == 200

    client.cookies.clear()
    assert client.post("/api/auth/login", json={"name": teacher["name"], "password": TEST_PASSWORD}).status_code == 401


def test_activating_an_unknown_account_is_a_404(client: TestClient, admin: str) -> None:
    as_admin(client, admin)

    assert client.patch(f"{USER_PATH}/{uuid4().hex}", json={"is_active": True}).status_code == 404


def test_a_teacher_cannot_flip_anyone_active(client: TestClient, admin: str) -> None:
    """自己把自己启停也不行 —— 这是管理能力，不是个人设置。"""
    teacher = _me(client)

    assert client.patch(f"{USER_PATH}/{teacher['id']}", json={"is_active": False}).status_code == 403


def test_an_admin_can_create_a_group_for_a_teacher(client: TestClient, admin: str) -> None:
    teacher = _me(client)
    as_admin(client, admin)

    response = client.post(GROUP_PATH, json={"name": _name("课题组"), "owner_id": teacher["id"]})

    assert response.status_code == 200, response.text
    assert response.json()["owner_id"] == teacher["id"]
    assert response.json()["invite_code"]


def test_a_group_needs_an_existing_owner(client: TestClient, admin: str) -> None:
    """组主是外键。编一个 uuid 进去的话，那个组从建出来就没人管得了。"""
    as_admin(client, admin)

    response = client.post(GROUP_PATH, json={"name": _name("课题组"), "owner_id": uuid4().hex})

    assert response.status_code == 404


def test_a_taken_group_name_is_refused(client: TestClient, admin: str) -> None:
    teacher = _me(client)
    as_admin(client, admin)
    name = _name("课题组")
    client.post(GROUP_PATH, json={"name": name, "owner_id": teacher["id"]})

    response = client.post(GROUP_PATH, json={"name": name, "owner_id": teacher["id"]})

    assert response.status_code == 422


def test_a_teacher_cannot_create_a_group(client: TestClient) -> None:
    teacher = _me(client)

    response = client.post(GROUP_PATH, json={"name": _name("课题组"), "owner_id": teacher["id"]})

    assert response.status_code == 403


def test_the_new_group_takes_students_in_by_its_invite_code(client: TestClient, admin: str) -> None:
    """建组与注册之间那条链路：管理员建组 → 教师发码 → 学生凭码进组。"""
    teacher = _me(client)
    as_admin(client, admin)
    code = client.post(GROUP_PATH, json={"name": _name("课题组"), "owner_id": teacher["id"]}).json()["invite_code"]
    client.cookies.clear()

    response = client.post(
        REGISTER_PATH, json={"name": _name("学生"), "email": _email(), "password": NEW_PASSWORD, "invite_code": code}
    )

    assert response.status_code == 200, response.text
    assert response.json()["is_active"] is True


def test_the_created_account_can_log_in_with_its_email(client: TestClient, admin: str) -> None:
    """**邮箱是第二把登录钥匙。**

    教师记得住自己的邮箱，未必记得住管理员当初给他起的用户名 —— 建号页填了邮箱
    却登不上，那个字段就只是名册上的装饰。
    """
    as_admin(client, admin)
    email = _email()
    client.post(USER_PATH, json={"name": _name("教师"), "email": email, "password": NEW_PASSWORD, "role": "teacher"})

    client.cookies.clear()
    response = client.post("/api/auth/login", json={"name": email, "password": NEW_PASSWORD})

    assert response.status_code == 200, response.text
    assert response.json()["email"] == email


def test_an_admin_can_override_a_quota(client: TestClient, admin: str) -> None:
    """配额调得动，且回读得到 —— 闸门读的就是这一列。"""
    as_admin(client, admin)
    created = client.post(
        USER_PATH, json={"name": _name("学生"), "email": _email(), "password": NEW_PASSWORD, "role": "student"}
    ).json()

    response = client.patch(f"{USER_PATH}/{created['id']}", json={"quota_tokens_daily": 4321})

    assert response.status_code == 200, response.text
    assert response.json()["quota_tokens_daily"] == 4321


def test_clearing_a_quota_override_returns_to_the_role_default(client: TestClient, admin: str) -> None:
    """**显式传 null 要能把配额清回默认档。**

    留空表示「跟着角色的默认档走」。若实现把 null 当成「这一项不改」，
    调过配额的人就再也回不去了 —— 而那种错读起来像是「保存没生效」。
    """
    as_admin(client, admin)
    created = client.post(
        USER_PATH, json={"name": _name("学生"), "email": _email(), "password": NEW_PASSWORD, "role": "student"}
    ).json()
    client.patch(f"{USER_PATH}/{created['id']}", json={"quota_tokens_daily": 4321})

    response = client.patch(f"{USER_PATH}/{created['id']}", json={"quota_tokens_daily": None})

    assert response.status_code == 200, response.text
    assert response.json()["quota_tokens_daily"] is None


def test_activating_still_works_on_its_own(client: TestClient, admin: str) -> None:
    """启停这条老路径不能被本期的扩展改坏 —— 它是激活入口，也是封禁入口。"""
    as_admin(client, admin)
    created = client.post(
        USER_PATH, json={"name": _name("学生"), "email": _email(), "password": NEW_PASSWORD, "role": "student"}
    ).json()

    response = client.patch(f"{USER_PATH}/{created['id']}", json={"is_active": False})

    assert response.status_code == 200, response.text
    assert response.json()["is_active"] is False


def test_the_system_page_reports_the_real_pool(client: TestClient, admin: str) -> None:
    """**沙箱池的数字要来自 broker，不是前端写死的 6 / 20。**

    写死的容量看板在满池时最没用 —— 它永远显示还有余量，而那正是有人要来问
    「为什么建不了会话」的时刻。
    """
    as_admin(client, admin)

    response = client.get("/api/admin/system")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["capacity"] > 0
    assert body["in_use"] >= 0
    assert body["broker_reachable"] is True


def test_a_teacher_cannot_see_the_system_page(client: TestClient) -> None:
    """系统状态是管理能力 —— 它透出的是整台机器的余量。"""
    assert client.get("/api/admin/system").status_code == 403
