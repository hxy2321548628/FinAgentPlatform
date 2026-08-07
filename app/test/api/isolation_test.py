"""多租户隔离的测试：拿 A 的身份去够 B 的东西，四条路径全部 404。

**403 也算没过。** 403 等于确认了「这个资源存在，只是不给你」，可以被用来一个个探
别人有哪些会话。不存在与不属于你必须是同一个回答。

**管理员不例外。** 它多的是管账号的能力，不是看别人会话的能力 —— 这条边界最容易
为了「方便排查问题」被悄悄破坏，一旦破坏就很难再收回来。
"""

from functools import partial
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from api.platform import Platform
from auth.password import PasswordHasher
from test.api.conftest import login, signup
from user.model import UserRole

# 一个别人的会话里能被够到的每一条路径。**逐条列出来而不是抽样**：
# 漏掉一条就是一个越权入口，而那种缺口不报错
BORROWED_PATH = (
    "/api/threads/{thread_id}/runs",
    "/api/runs/{run_id}",
    "/api/runs/{run_id}/events",
    "/api/artifacts/{thread_id}/chart.png",
)


@pytest.fixture
def victim(client: TestClient) -> dict[str, str]:
    """先用当前登录的人造出一个会话与一个 run，它们就是「别人的东西」。"""
    thread_id = client.post("/api/threads").json()["id"]
    run_id = client.post(f"/api/threads/{thread_id}/runs", json={"content": "算个波动率"}).json()["id"]
    return {"thread_id": thread_id, "run_id": run_id}


def _become(client: TestClient, platform: Platform, hasher: PasswordHasher, role: UserRole) -> None:
    """换成另一个人登录。同一个客户端，换一份 Cookie。"""
    name = f"{role.value}-{uuid4().hex[:8]}"
    signup(client, platform, hasher, name=name, role=role)
    client.cookies.clear()
    login(client, name)


@pytest.mark.parametrize("path", BORROWED_PATH)
def test_another_user_gets_404_on_every_path(
    client: TestClient, platform: Platform, hasher: PasswordHasher, victim: dict[str, str], path: str
) -> None:
    _become(client, platform, hasher, UserRole.TEACHER)

    response = _reach(client, path, victim)

    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.parametrize("path", BORROWED_PATH)
def test_an_admin_gets_404_too(
    client: TestClient, platform: Platform, hasher: PasswordHasher, victim: dict[str, str], path: str
) -> None:
    """架构明确管理员不能查看他人的会话内容与上传数据。"""
    _become(client, platform, hasher, UserRole.ADMIN)

    assert _reach(client, path, victim).status_code == 404


def test_another_user_cannot_upload_into_someone_elses_thread(
    client: TestClient, platform: Platform, hasher: PasswordHasher, victim: dict[str, str]
) -> None:
    _become(client, platform, hasher, UserRole.TEACHER)

    response = client.post(
        f"/api/threads/{victim['thread_id']}/files",
        files={"file": ("holdings.csv", b"a,b\n", "text/csv")},
    )

    assert response.status_code == 404


def test_the_owner_still_reaches_everything(client: TestClient, victim: dict[str, str]) -> None:
    """上面几条不能是「谁都够不着」—— 主人自己必须照常拿得到。"""
    assert client.get(f"/api/runs/{victim['run_id']}").status_code == 200
    assert client.post(f"/api/threads/{victim['thread_id']}/runs", json={"content": "再问一次"}).status_code == 202


def test_a_run_is_written_with_its_owner(client: TestClient, platform: Platform, victim: dict[str, str]) -> None:
    """`runs.user_id` 由提交这个唯一入口填，不做触发器 —— 那就得验它真的填了。

    直接问仓储而不是看响应体：响应里没有 user_id，而要验的正是库里那一列。
    """
    identity = client.get("/api/auth/me").json()["id"]
    assert client.portal is not None

    found = client.portal.call(partial(platform.repository.get, victim["run_id"], user_id=identity))

    assert found is not None


def _reach(client: TestClient, path: str, victim: dict[str, str]) -> httpx.Response:
    """按路径够一次别人的东西。提交分析是 POST，其余都是 GET。"""
    target = path.format(**victim)
    response: httpx.Response = (
        client.post(target, json={"content": "借你的会话一用"}) if target.endswith("/runs") else client.get(target)
    )
    return response
