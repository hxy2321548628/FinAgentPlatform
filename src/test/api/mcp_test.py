"""MCP 目录端点：申请、放行、启停，以及提交侧那两道关。

**这一族守的是「列表过滤对了而提交侧忘了查」那个漏洞形状** —— `P7①` `P8⑤` `P9③`
各踩过一次。因此每条闸门都验两侧：目录列表看不看得见，以及提交时能不能勾上。
"""

from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.platform import Platform
from app.auth.password import PasswordHasher
from app.user.model import UserRole
from app.user.repository import User
from test.api.agent_test import as_user
from test.api.conftest import login, signup

MCP_PATH = "/api/mcp"
ADMIN_PATH = "/api/mcp/admin"
THREAD_PATH = "/api/threads"

Body = dict[str, object]


def application(name: str | None = None, /, **override: object) -> Body:
    body: Body = {
        "name": name or f"paper-{uuid4().hex[:8]}",
        "description": "校内论文库检索",
        "url": "https://mcp.example.edu/mcp",
        "transport": "streamable_http",
        "tool_names": ["search_paper"],
        "latency_note": "典型 1 秒，最坏 10 秒",
        "stores_user_data": False,
        "sends_data_out": True,
        "has_write_operation": False,
    }
    body.update(override)
    return body


def apply_for(client: TestClient, **override: object) -> Body:
    response = client.post(MCP_PATH, json=application(None, **override))
    assert response.status_code == 201, response.text
    created: Body = response.json()
    return created


def approve(client: TestClient, server_id: str) -> None:
    response = client.post(f"{ADMIN_PATH}/{server_id}/decision", json={"approved": True})
    assert response.status_code == 202, response.text


@pytest.fixture
def administrator(client: TestClient, platform: Platform, hasher: PasswordHasher) -> User:
    return signup(client, platform, hasher, name=f"管理员-{uuid4().hex[:8]}", role=UserRole.ADMIN)


@pytest.fixture
def teacher(client: TestClient, platform: Platform, hasher: PasswordHasher) -> User:
    return signup(client, platform, hasher, name=f"教师-{uuid4().hex[:8]}", role=UserRole.TEACHER)


@pytest.fixture
def reviewer(client: TestClient, platform: Platform, hasher: PasswordHasher) -> User:
    return signup(client, platform, hasher, name=f"审核员-{uuid4().hex[:8]}", role=UserRole.REVIEWER)


def make_thread(client: TestClient) -> str:
    response = client.post(THREAD_PATH, json={})
    assert response.status_code == 201, response.text
    identifier: str = response.json()["id"]
    return identifier


def submit_with(client: TestClient, thread_id: str, server_ids: list[str]) -> httpx.Response:
    submitted: httpx.Response = client.post(
        f"{THREAD_PATH}/{thread_id}/runs",
        json={"content": "查一篇波动率的论文", "agent_config": {"mcps": server_ids}},
    )
    return submitted


async def test_a_fresh_application_is_invisible_and_unusable(
    client: TestClient, teacher: User, platform: Platform
) -> None:
    """`P10②` 第一道与第二道关：目录里看不到它，提交侧也勾不上。"""
    as_user(client, teacher)
    created = apply_for(client)
    thread_id = make_thread(client)

    catalog = client.get(MCP_PATH).json()
    rejected = submit_with(client, thread_id, [str(created["id"])])

    assert created["status"] == "pending"
    assert str(created["id"]) not in [str(one["id"]) for one in catalog]
    assert rejected.status_code == 422, rejected.text
    # 一行 run 都不该多出来：解析失败必须发生在投递之前
    assert client.get(f"{THREAD_PATH}/{thread_id}/runs").json()["items"] == []


async def test_a_reviewer_can_approve_an_mcp(client: TestClient, teacher: User, reviewer: User) -> None:
    """审核员审 MCP 与审 agent、skill 是同一档权限（2026-08-16 改）。

    此前这里断言的是 403：理由是「放行外网地址是安全边界决定，不是内容合规判断」。
    改成同一档之后，那条理由不再成立 —— 边界重新划在**审核与运维之间**，
    而不是划在资源类型之间。
    """
    as_user(client, teacher)
    created = apply_for(client)

    as_user(client, reviewer)
    decided = client.post(f"{ADMIN_PATH}/{created['id']}/decision", json={"approved": True})
    queue = client.get(ADMIN_PATH)

    assert decided.status_code == 202, decided.text
    assert queue.status_code == 200, queue.text
    assert str(created["id"]) in [str(one["id"]) for one in queue.json()]


async def test_a_reviewer_cannot_disable_or_probe_an_mcp(
    client: TestClient, teacher: User, reviewer: User, administrator: User
) -> None:
    """**审核员审得了，但停不了也探不了。**

    启停与探活是运维动作：它们改的是一个已经放行的服务此刻通不通，而不是
    「这条申请该不该放行」。审核员多拿一样就离 admin 的别名近一步，
    这个角色存在的意义正是它比 admin 少。
    """
    as_user(client, teacher)
    created = apply_for(client)
    as_user(client, administrator)
    approve(client, str(created["id"]))

    as_user(client, reviewer)
    disabled = client.post(f"{ADMIN_PATH}/{created['id']}/enabled", json={"enabled": False, "reason": "试试"})
    probed = client.post(f"{ADMIN_PATH}/{created['id']}/probe")

    assert disabled.status_code == 403, disabled.text
    assert probed.status_code == 403, probed.text


async def test_an_approved_server_becomes_visible_and_selectable(
    client: TestClient, teacher: User, administrator: User
) -> None:
    """两道关都要开：目录里出现，且提交侧解析得出来。"""
    as_user(client, teacher)
    created = apply_for(client)

    as_user(client, administrator)
    approve(client, str(created["id"]))

    as_user(client, teacher)
    catalog = client.get(MCP_PATH).json()
    thread_id = make_thread(client)
    accepted = submit_with(client, thread_id, [str(created["id"])])

    assert str(created["id"]) in [str(one["id"]) for one in catalog]
    assert accepted.status_code == 202, accepted.text
    snapshot = accepted.json()["agent_config"]["mcps"]
    assert snapshot == [{"server_id": created["id"], "name": created["name"]}]


async def test_an_application_declaring_write_operations_cannot_be_approved(
    client: TestClient, teacher: User, administrator: User
) -> None:
    """D3 的硬闸门：F8 / F9 落地之前，声明有写操作的一律批不了。

    **这是本期唯一一条「不能靠人记住」的规则** —— 做成闸门之后，「接第一个带写操作
    的 MCP 前必须重定 F8/F9」这件事就不会被悄悄跨过。
    """
    as_user(client, teacher)
    created = apply_for(client, has_write_operation=True)

    as_user(client, administrator)
    refused = client.post(f"{ADMIN_PATH}/{created['id']}/decision", json={"approved": True})

    assert refused.status_code == 422, refused.text
    assert "写操作" in refused.json()["error"]["message"]
    # 拒绝它倒是可以 —— 闸门挡的是放行，不是处理
    assert (
        client.post(
            f"{ADMIN_PATH}/{created['id']}/decision",
            json={"approved": False, "reason": "先把写操作那部分拆出去"},
        ).status_code
        == 202
    )


async def test_a_rejection_needs_a_reason(client: TestClient, teacher: User, administrator: User) -> None:
    as_user(client, teacher)
    created = apply_for(client)

    as_user(client, administrator)
    refused = client.post(f"{ADMIN_PATH}/{created['id']}/decision", json={"approved": False})

    assert refused.status_code == 422, refused.text


async def test_a_disabled_server_drops_out_of_both_the_catalog_and_the_submit_path(
    client: TestClient, teacher: User, administrator: User
) -> None:
    """停用同样要两侧都生效，否则勾一个连不上的服务只会浪费一次装配。"""
    as_user(client, teacher)
    created = apply_for(client)
    as_user(client, administrator)
    approve(client, str(created["id"]))

    stopped = client.post(f"{ADMIN_PATH}/{created['id']}/enabled", json={"enabled": False, "reason": "对方在升级"})

    as_user(client, teacher)
    catalog = client.get(MCP_PATH).json()
    thread_id = make_thread(client)
    refused = submit_with(client, thread_id, [str(created["id"])])

    assert stopped.status_code == 202, stopped.text
    assert stopped.json()["disabled_reason"] == "对方在升级"
    assert str(created["id"]) not in [str(one["id"]) for one in catalog]
    assert refused.status_code == 422, refused.text


async def test_more_than_the_limit_is_a_gate_not_a_hint(client: TestClient, teacher: User, administrator: User) -> None:
    """`MAX_MCP_SERVER` 是闸门：超了当场 422，不是悄悄截断成前三个。"""
    as_user(client, teacher)
    created = [apply_for(client) for _ in range(4)]
    as_user(client, administrator)
    for one in created:
        approve(client, str(one["id"]))

    as_user(client, teacher)
    thread_id = make_thread(client)
    refused = submit_with(client, thread_id, [str(one["id"]) for one in created])

    assert refused.status_code == 422, refused.text


async def test_a_server_declaring_a_builtin_tool_name_cannot_be_selected(
    client: TestClient, teacher: User, administrator: User
) -> None:
    """上架清单里就与内置工具重名的，勾选那一刻就该拦下。

    **这道检查会过期，因此它不是唯一的防线** —— 装配层拿到真实工具之后还要再剔一次。
    放在这里只是为了让教师当场知道，而不是跑完一次分析才发现工具没生效。
    """
    as_user(client, teacher)
    created = apply_for(client, tool_names=["read_file"])
    as_user(client, administrator)
    approve(client, str(created["id"]))

    as_user(client, teacher)
    thread_id = make_thread(client)
    refused = submit_with(client, thread_id, [str(created["id"])])

    assert refused.status_code == 422, refused.text
    assert "read_file" in refused.json()["error"]["message"]


async def test_the_catalog_never_hands_out_credentials(client: TestClient, teacher: User, administrator: User) -> None:
    """库里存的本来就只有键名，而这张表要被前端读 —— 键名也不出库。"""
    as_user(client, teacher)
    created = apply_for(client, credential_key="market-data")
    as_user(client, administrator)
    approve(client, str(created["id"]))

    as_user(client, teacher)
    card = next(one for one in client.get(MCP_PATH).json() if one["id"] == created["id"])

    assert card["has_credential"] is True
    assert "credential_key" not in card
    assert "market-data" not in str(card)


async def test_a_non_http_address_is_refused(client: TestClient, teacher: User) -> None:
    """Stdio 挡在枚举上，而一个 `file://` 地址挡在这里。"""
    as_user(client, teacher)

    refused = client.post(MCP_PATH, json=application(url="file:///etc/passwd"))

    assert refused.status_code == 422, refused.text


async def test_stdio_is_not_a_value_anyone_can_send(client: TestClient, teacher: User) -> None:
    """**枚举里根本没有这个取值**，不是靠一条校验挡住的。"""
    as_user(client, teacher)

    refused = client.post(MCP_PATH, json=application(transport="stdio"))

    assert refused.status_code == 422, refused.text


async def test_only_an_administrator_sees_the_queue(client: TestClient, teacher: User, administrator: User) -> None:
    as_user(client, teacher)
    created = apply_for(client)

    refused = client.get(ADMIN_PATH)
    as_user(client, administrator)
    queue = client.get(ADMIN_PATH)

    assert refused.status_code == 403
    assert queue.status_code == 200
    listed = [one for one in queue.json() if one["id"] == created["id"]]
    assert listed[0]["submitter_name"] == teacher.name
    assert listed[0]["failure_count"] == 0


async def test_the_application_leaves_a_review_trail(
    client: TestClient, teacher: User, administrator: User, platform: Platform
) -> None:
    """审核记录复用 `reviews`：谁提的、谁批的、什么时候，那张表本来就记这些。"""
    from app.preset.model import ResourceKind

    as_user(client, teacher)
    created = apply_for(client)
    as_user(client, administrator)
    approve(client, str(created["id"]))

    assert client.portal is not None
    trail = client.portal.call(
        lambda: platform.review.list_for_target([str(created["id"])], target_kind=ResourceKind.MCP)
    )

    assert len(trail) == 1
    assert trail[0].status.value == "approved"
    assert trail[0].submitted_by == teacher.id
    assert trail[0].reviewed_by == administrator.id


async def test_a_second_login_is_not_needed_to_re_apply_a_rejected_name(
    client: TestClient, teacher: User, administrator: User
) -> None:
    """一次被拒不该把名字永久占住。"""
    name = f"paper-{uuid4().hex[:8]}"
    as_user(client, teacher)
    first = apply_for(client, name=name)
    duplicate = client.post(MCP_PATH, json=application(name))

    as_user(client, administrator)
    client.post(f"{ADMIN_PATH}/{first['id']}/decision", json={"approved": False, "reason": "地址不对"})

    as_user(client, teacher)
    again = client.post(MCP_PATH, json=application(name))

    assert duplicate.status_code == 422
    assert again.status_code == 201, again.text


async def test_logging_in_is_required_at_all(client: TestClient) -> None:
    client.cookies.clear()

    assert client.get(MCP_PATH).status_code == 401


def test_an_unknown_server_is_a_miss(client: TestClient, administrator: User) -> None:
    login(client, administrator.name)

    assert client.post(f"{ADMIN_PATH}/{uuid4().hex}/probe").status_code == 404
