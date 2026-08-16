"""注册端点的测试。

注册与登录是平台仅有的两个未登录也能打的端口，因此这里除了「能不能建出账号」，
还要验两件事：**建出来的一律是学生**，以及**错误的邀请码不留下半个账号**。
"""

from functools import partial
from uuid import uuid4

from fastapi.testclient import TestClient

from api.platform import Platform
from api.schema import MIN_PASSWORD_LENGTH
from auth.session import COOKIE_NAME
from test.api.conftest import TEST_PASSWORD, make_group
from test.conftest import json_log
from user.model import UserRole

REGISTER_PATH = "/api/auth/register"

NEW_PASSWORD = "口令-register"


def _email() -> str:
    return f"{uuid4().hex[:8]}@zuel.edu.cn"


def _name() -> str:
    return f"新同学-{uuid4().hex[:8]}"


def _owner_id(client: TestClient) -> str:
    identifier: str = client.get("/api/auth/me").json()["id"]
    return identifier


def test_registering_with_an_invite_code_joins_that_group(client: TestClient, platform: Platform) -> None:
    group = make_group(client, platform, owner_id=_owner_id(client))
    name = _name()

    response = client.post(
        REGISTER_PATH,
        json={"name": name, "email": _email(), "password": NEW_PASSWORD, "invite_code": group.invite_code},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["is_active"] is True
    assert body["group_name"] == group.name
    assert body["role"] == UserRole.STUDENT.value


def test_someone_who_used_an_invite_code_can_log_in_at_once(client: TestClient, platform: Platform) -> None:
    """凭码注册就是凭码准入 —— 再让管理员点一次没有任何意义。"""
    group = make_group(client, platform, owner_id=_owner_id(client))
    name = _name()
    client.post(
        REGISTER_PATH,
        json={"name": name, "email": _email(), "password": NEW_PASSWORD, "invite_code": group.invite_code},
    )

    client.cookies.clear()
    response = client.post("/api/auth/login", json={"name": name, "password": NEW_PASSWORD})

    assert response.status_code == 200, response.text


def test_someone_who_used_an_invite_code_is_on_the_roster(client: TestClient, platform: Platform) -> None:
    group = make_group(client, platform, owner_id=_owner_id(client))
    client.post(
        REGISTER_PATH,
        json={"name": _name(), "email": _email(), "password": NEW_PASSWORD, "invite_code": group.invite_code},
    )
    assert client.portal is not None

    roster = client.portal.call(partial(platform.group.list_member, group.id))

    assert len(roster) == 2


def test_registering_without_a_code_cannot_log_in_yet(client: TestClient) -> None:
    """没码的账号建得出来但登不上，等管理员激活。"""
    name = _name()
    response = client.post(REGISTER_PATH, json={"name": name, "email": _email(), "password": NEW_PASSWORD})

    assert response.status_code == 200, response.text
    assert response.json()["is_active"] is False
    assert response.json()["group_name"] is None

    client.cookies.clear()
    assert client.post("/api/auth/login", json={"name": name, "password": NEW_PASSWORD}).status_code == 401


def test_a_wrong_invite_code_is_refused(client: TestClient) -> None:
    response = client.post(
        REGISTER_PATH, json={"name": _name(), "email": _email(), "password": NEW_PASSWORD, "invite_code": "NOSUCH99"}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_a_wrong_invite_code_leaves_no_account_behind(client: TestClient, platform: Platform) -> None:
    """先验码再建号。反过来的话，码打错一个字就留下一个自己登不上、管理员也不认识的号。"""
    name = _name()
    client.post(
        REGISTER_PATH, json={"name": name, "email": _email(), "password": NEW_PASSWORD, "invite_code": "NOSUCH99"}
    )
    assert client.portal is not None

    assert client.portal.call(partial(platform.user.find_by_name, name)) is None


def test_a_taken_name_is_refused(client: TestClient) -> None:
    name = _name()
    client.post(REGISTER_PATH, json={"name": name, "email": _email(), "password": NEW_PASSWORD})

    response = client.post(REGISTER_PATH, json={"name": name, "email": _email(), "password": NEW_PASSWORD})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_a_registered_account_is_always_a_student(client: TestClient) -> None:
    """自选角色等于自选配额档 —— 而配额是 teacher 与 student 唯一的实质差别。"""
    response = client.post(
        REGISTER_PATH,
        json={"name": _name(), "email": _email(), "password": NEW_PASSWORD, "role": UserRole.TEACHER.value},
    )

    assert response.status_code == 200, response.text
    assert response.json()["role"] == UserRole.STUDENT.value


def test_a_short_password_is_refused(client: TestClient) -> None:
    response = client.post(REGISTER_PATH, json={"name": _name(), "password": "x" * (MIN_PASSWORD_LENGTH - 1)})

    assert response.status_code == 422


def test_registering_does_not_hand_out_a_session(client: TestClient, platform: Platform) -> None:
    """注册完自己去登录。少一条「未登录也能拿到 Cookie」的路径就少一片要防的面。"""
    group = make_group(client, platform, owner_id=_owner_id(client))
    client.cookies.clear()

    response = client.post(
        REGISTER_PATH,
        json={"name": _name(), "email": _email(), "password": NEW_PASSWORD, "invite_code": group.invite_code},
    )

    assert response.status_code == 200, response.text
    assert COOKIE_NAME not in response.cookies


def test_registering_is_open_to_anonymous_callers(client: TestClient) -> None:
    """还没有账号的人正是要走这个端口，它不能要求先登录。"""
    client.cookies.clear()

    assert (
        client.post(REGISTER_PATH, json={"name": _name(), "email": _email(), "password": NEW_PASSWORD}).status_code
        == 200
    )


def test_the_password_never_shows_up_in_the_log(client: TestClient) -> None:
    with json_log("api.route.auth") as recorded:
        client.post(REGISTER_PATH, json={"name": _name(), "email": _email(), "password": NEW_PASSWORD})
        client.post(
            REGISTER_PATH,
            json={"name": _name(), "email": _email(), "password": TEST_PASSWORD, "invite_code": "NOSUCH99"},
        )

    assert recorded
    for line in recorded:
        assert NEW_PASSWORD not in str(line)
        assert TEST_PASSWORD not in str(line)
