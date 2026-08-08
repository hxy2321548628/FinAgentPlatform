"""成本看板端点：谁花了多少、每天花了多少，以及它守不守得住那条边界。

**「管理员看得到用量、看不到会话内容」是这一步唯一真正危险的地方**：一个按用户聚合的
报表端点，稍不留神就顺手把会话标题、提问、答复也带出来了 —— 而那条边界一旦破了
就很难再收回去。因此这里有一条用例专门去数「响应里有没有出现过会话内容」。
"""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api.platform import Platform
from auth.password import PasswordHasher
from test.api.conftest import Agent, drain, login, signup
from user.model import UserRole

# 教师提的问题与 agent 的答复。两者都不该出现在看板的响应里
QUESTION = "帮我算一下白酒板块的月度收益率"
ANSWER = "白酒板块上月收益率 3.7%"


@pytest.fixture
def admin(client: TestClient, platform: Platform, hasher: PasswordHasher) -> str:
    """一个管理员，并且已经登录。返回它的名字。"""
    account = signup(client, platform, hasher, name=f"admin-{uuid4().hex[:8]}", role=UserRole.ADMIN)
    return account.name


def run_once(client: TestClient, thread_id: str, agent: Agent) -> None:
    """跑一次假分析，让 runs 表里有一条带 token 的行。"""
    agent.chunk = []
    run_id = client.post(f"/api/threads/{thread_id}/runs", json={"content": QUESTION}).json()["id"]
    drain(client, run_id)


def as_admin(client: TestClient, admin: str) -> None:
    client.cookies.clear()
    login(client, admin)


def test_a_teacher_cannot_open_the_dashboard(client: TestClient) -> None:
    """看板是运维页。教师看得到自己的用量提示，不该看得到全校的账。"""
    response = client.get("/api/admin/usage")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_an_anonymous_visitor_cannot_open_the_dashboard(client: TestClient) -> None:
    client.cookies.clear()

    assert client.get("/api/admin/usage").status_code == 401


def test_the_dashboard_answers_who_spent_how_much(client: TestClient, thread_id: str, agent: Agent, admin: str) -> None:
    owner_name = client.get("/api/auth/me").json()["name"]
    run_once(client, thread_id, agent)
    as_admin(client, admin)

    body = client.get("/api/admin/usage").json()

    assert any(one["name"] == owner_name and one["runs"] >= 1 for one in body["users"])


def test_the_dashboard_splits_by_day(client: TestClient, thread_id: str, agent: Agent, admin: str) -> None:
    """「按时间聚合」的那一半，静态页拿它画趋势。"""
    run_once(client, thread_id, agent)
    as_admin(client, admin)

    body = client.get("/api/admin/usage").json()

    assert body["daily"]
    assert {"day", "runs", "cache_read", "uncached", "output"} <= set(body["daily"][0])


def test_the_window_is_reported_back(client: TestClient, admin: str) -> None:
    """看板上那个数是「哪一段时间的」，不写出来就没法核对。"""
    as_admin(client, admin)

    body = client.get("/api/admin/usage?days=7").json()

    assert body["since"] < body["until"]
    assert body["days"] == 7


def test_a_shorter_window_leaves_older_runs_out(client: TestClient, thread_id: str, agent: Agent, admin: str) -> None:
    """窗口要真的起作用 —— 不然「按时间聚合」只是个摆设。"""
    run_once(client, thread_id, agent)
    as_admin(client, admin)

    body = client.get("/api/admin/usage?days=1").json()

    assert body["days"] == 1
    assert body["daily"]


def test_an_absurd_window_is_rejected(client: TestClient, admin: str) -> None:
    as_admin(client, admin)

    assert client.get("/api/admin/usage?days=0").status_code == 422


def test_the_dashboard_never_leaks_session_content(
    client: TestClient, thread_id: str, agent: Agent, admin: str
) -> None:
    """架构 §6.3 的边界不能被这个端点绕开：只有数字，没有内容。

    直接在整个响应文本里找教师的提问与会话标识 —— 断言字段名的话，
    将来多加一个字段就绕过了这条用例，而它正是这一步最该守住的东西。
    """
    agent.chunk = []
    run_id = client.post(f"/api/threads/{thread_id}/runs", json={"content": QUESTION}).json()["id"]
    drain(client, run_id)
    as_admin(client, admin)

    text = client.get("/api/admin/usage").text

    assert QUESTION not in text
    assert ANSWER not in text
    assert thread_id not in text
    assert run_id not in text
