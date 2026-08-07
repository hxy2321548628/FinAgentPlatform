"""认证端点的测试：登录、登出、我是谁，以及「没登录就什么都不给」。

**Cookie 全程交给客户端自己收发**，不手工拼请求头 —— 那正是浏览器要走的路径，
手工拼会绕开 `HttpOnly` / `SameSite` 这些真正要验的属性。
"""

from functools import partial
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from sqlalchemy import text

from api.platform import Platform
from api.route.auth import COOKIE_PATH, COOKIE_SAME_SITE
from auth.password import PasswordHasher
from auth.session import COOKIE_NAME, KEY_PREFIX
from test.api.conftest import TEST_PASSWORD, login, signup
from test.conftest import json_log
from user.model import UserRole

# 未登录时业务端点的全部入口。**逐条列出来而不是抽样**：漏挂一个端点就是一个
# 不需要登录的入口，而那种缺口不报错
BUSINESS_PATH = (
    ("POST", "/api/threads"),
    ("POST", "/api/threads/whatever/runs"),
    ("GET", "/api/runs/whatever"),
    ("GET", "/api/runs/whatever/events"),
    ("GET", "/api/artifacts/whatever"),
)


def _cookie_header(client: TestClient) -> str:
    """登录响应里那一行原始的 `set-cookie`，属性都在上面。"""
    response = client.post("/api/auth/login", json={"name": _current_name(client), "password": TEST_PASSWORD})
    header: str = response.headers["set-cookie"]
    return header


def _current_name(client: TestClient) -> str:
    name: str = client.get("/api/auth/me").json()["name"]
    return name


def test_logging_in_answers_who_i_am(client: TestClient) -> None:
    response = client.get("/api/auth/me")

    assert response.status_code == 200
    body = response.json()
    assert body["role"] == UserRole.TEACHER.value
    assert body["name"]
    # 「所属组」本期不返回：groups 两张表不建，恒空的字段只会让前端以为将来会有东西
    assert "groups" not in body


def test_the_cookie_is_http_only_and_same_site_lax(client: TestClient) -> None:
    """XSS 偷不走（HttpOnly），跨站请求带不上（SameSite）。两条都在这一行响应头里。"""
    header = _cookie_header(client).lower()

    assert "httponly" in header
    assert f"samesite={COOKIE_SAME_SITE}" in header
    assert f"path={COOKIE_PATH}" in header


def test_the_cookie_carries_no_identity_of_its_own(client: TestClient) -> None:
    """Cookie 里只有一个不可猜的令牌 —— 用户名、角色一个字都不在上面。"""
    token = client.cookies[COOKIE_NAME]
    name = _current_name(client)

    assert name not in token
    assert UserRole.TEACHER.value not in token


def test_the_session_lives_in_redis_with_a_sliding_expiry(client: TestClient, live_cache: Redis) -> None:
    """7 天滑动过期：键上要有 TTL，而不是永不过期。

    **查 Redis 也要回到应用那条循环里**：连接绑在创建它的循环上，在 pytest 这条
    循环里读同一个客户端会挂在读上，而报出来的是「future 属于另一个循环」。
    """
    token = client.cookies[COOKIE_NAME]
    assert client.portal is not None

    ttl = client.portal.call(partial(live_cache.ttl, f"{KEY_PREFIX}{token}"))

    assert ttl > 0


def test_logging_out_kills_the_same_cookie_at_once(client: TestClient) -> None:
    """光清浏览器那一侧不算登出 —— 令牌本身必须立刻作废。"""
    token = client.cookies[COOKIE_NAME]

    assert client.post("/api/auth/logout").status_code == 204

    # 客户端那一侧的 Cookie 已经被删了，因此手工把同一个令牌塞回去，验它真的不认了
    client.cookies.set(COOKIE_NAME, token)
    assert client.get("/api/auth/me").status_code == 401


@pytest.mark.parametrize(("method", "path"), BUSINESS_PATH)
def test_business_endpoints_refuse_anonymous_callers(client: TestClient, method: str, path: str) -> None:
    client.cookies.clear()

    response = client.request(method, path)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_a_forged_token_is_not_accepted(client: TestClient) -> None:
    client.cookies.set(COOKIE_NAME, uuid4().hex)

    assert client.get("/api/auth/me").status_code == 401


def test_a_wrong_password_is_refused(client: TestClient) -> None:
    name = _current_name(client)

    response = client.post("/api/auth/login", json={"name": name, "password": "错的口令"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_an_unknown_user_gets_the_same_answer_as_a_wrong_password(client: TestClient) -> None:
    """两者分开说，等于告诉试探的人「这个用户名是存在的」。"""
    wrong = client.post("/api/auth/login", json={"name": _current_name(client), "password": "错的口令"})
    unknown = client.post("/api/auth/login", json={"name": f"没有这个人-{uuid4().hex}", "password": TEST_PASSWORD})

    assert wrong.status_code == unknown.status_code
    assert wrong.json() == unknown.json()


def test_the_password_never_shows_up_in_the_log(client: TestClient, platform: Platform, hasher: PasswordHasher) -> None:
    """明文口令只在校验那一刻存在，落库的是哈希，日志里一个字都不该有。"""
    name = f"teacher-{uuid4().hex[:8]}"
    signup(client, platform, hasher, name=name)

    with json_log("api.route.auth") as recorded:
        login(client, name)
        client.post("/api/auth/login", json={"name": name, "password": "另一个错口令"})

    assert recorded
    for line in recorded:
        assert TEST_PASSWORD not in str(line)
        assert "另一个错口令" not in str(line)


def test_only_the_hash_reaches_the_database(client: TestClient, platform: Platform, hasher: PasswordHasher) -> None:
    name = f"teacher-{uuid4().hex[:8]}"
    signup(client, platform, hasher, name=name)
    assert client.portal is not None

    credential = client.portal.call(partial(platform.user.find_by_name, name))

    assert credential is not None
    assert TEST_PASSWORD not in credential.password_hash
    assert credential.password_hash.startswith("$argon2id$")


def test_the_event_stream_accepts_the_same_cookie(client: TestClient, thread_id: str) -> None:
    """SSE 走的是另一套客户端，凭据最容易在这里漏掉 —— 而本平台的核心交互全在 SSE 上。"""
    run_id = client.post(f"/api/threads/{thread_id}/runs", json={"content": "问题"}).json()["id"]

    with client.stream("GET", f"/api/runs/{run_id}/events") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")


def test_the_event_stream_refuses_a_caller_without_the_cookie(client: TestClient, thread_id: str) -> None:
    run_id = client.post(f"/api/threads/{thread_id}/runs", json={"content": "问题"}).json()["id"]
    client.cookies.clear()

    response = client.get(f"/api/runs/{run_id}/events")

    assert response.status_code == 401


def test_a_disabled_account_cannot_log_in(client: TestClient, platform: Platform, hasher: PasswordHasher) -> None:
    name = f"student-{uuid4().hex[:8]}"
    user = signup(client, platform, hasher, name=name, role=UserRole.STUDENT)
    assert client.portal is not None
    client.portal.call(_disable, platform, user.id)

    response = client.post("/api/auth/login", json={"name": name, "password": TEST_PASSWORD})

    assert response.status_code == 401


async def _disable(platform: Platform, user_id: str) -> None:
    """把一个账号停用。本期没有管理接口，测试直接改库。"""
    async with platform.engine.begin() as connection:
        await connection.execute(text("UPDATE users SET is_active = false WHERE id = :id"), {"id": user_id})
