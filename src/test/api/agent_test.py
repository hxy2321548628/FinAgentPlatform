"""智能体目录端点：三个列表、我的那一族、审核，以及引用真的生效。

**这一族里最危险的是「多看见了一条」**：别组的老师在列表里刷到一个不该看到的提示词，
既不报错也不会有人来报。因此每一条可见性用例都是双向的，且**提交侧单独断一次** ——
列表过滤对了而提交侧忘了查，是最典型的漏洞形状：拿到 id 就能引用别人的提示词。
"""

from functools import partial
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.platform import Platform
from app.auth.password import PasswordHasher
from app.group.repository import Group
from app.user.model import UserRole
from app.user.repository import User
from test.api.conftest import login, make_group, signup

AGENT_PATH = "/api/agents"

REVIEW_PATH = "/api/reviews"

CAT_PROMPT = "每一句都以「喵」开头。"

Body = dict[str, object]


@pytest.fixture
def author(client: TestClient) -> dict[str, str]:
    """`client` 一开始登着的那个教师，本文件里的作者 A。"""
    body: dict[str, str] = client.get("/api/auth/me").json()
    return body


@pytest.fixture
def group(client: TestClient, platform: Platform, author: dict[str, str]) -> Group:
    """作者带的组 G1。"""
    return make_group(client, platform, owner_id=author["id"])


@pytest.fixture
def teammate(client: TestClient, platform: Platform, hasher: PasswordHasher, group: Group) -> User:
    """同组的 B，**还没登录**。"""
    member = signup(client, platform, hasher, name=f"同组-{uuid4().hex[:8]}")
    assert client.portal is not None
    client.portal.call(partial(platform.group.add_member, group_id=group.id, user_id=member.id))
    return member


@pytest.fixture
def outsider(client: TestClient, platform: Platform, hasher: PasswordHasher) -> User:
    """别组的 C，**真的在另一个组里** —— 都在同一个组的话，「别组看不见」根本没被触发过。"""
    stranger = signup(client, platform, hasher, name=f"别组-{uuid4().hex[:8]}")
    other = make_group(client, platform, owner_id=stranger.id)
    assert client.portal is not None
    assert client.portal.call(partial(platform.group.is_member, group_id=other.id, user_id=stranger.id)) is True
    return stranger


@pytest.fixture
def reviewer(client: TestClient, platform: Platform, hasher: PasswordHasher) -> User:
    """一个审核员，**还没登录**。"""
    return signup(client, platform, hasher, name=f"审核-{uuid4().hex[:8]}", role=UserRole.REVIEWER)


def as_user(client: TestClient, user: User) -> None:
    client.cookies.clear()
    login(client, user.name)


def create_agent(client: TestClient, *, prompt: str = CAT_PROMPT) -> Body:
    response = client.post(
        AGENT_PATH,
        json={
            "name": f"喵语老师-{uuid4().hex[:8]}",
            "description": "说话带喵",
            "subject": "金融学",
            "system_prompt": prompt,
        },
    )
    assert response.status_code == 201, response.text
    created: Body = response.json()
    return created


def create_skill(client: TestClient, name: str) -> str:
    content = f"---\nname: {name}\ndescription: agent 自带能力\n---\n\n# {name}\n".encode()
    response = client.post(
        "/api/skills",
        files={"file": (f"{name}.md", content, "text/markdown")},
    )
    assert response.status_code == 201, response.text
    skill_id = str(response.json()["id"])
    assert client.post(f"/api/skills/{skill_id}/versions").status_code == 201
    return skill_id


def release(client: TestClient, agent_id: str) -> Body:
    response = client.post(f"{AGENT_PATH}/{agent_id}/versions")
    assert response.status_code == 201, response.text
    released: Body = response.json()
    return released


def share(client: TestClient, agent_id: str, group: Group) -> None:
    response = client.put(f"{AGENT_PATH}/{agent_id}/sharing", json={"visibility": "group", "group_ids": [group.id]})
    assert response.status_code == 200, response.text


def submit_review(client: TestClient, agent_id: str) -> str:
    response = client.post(f"{AGENT_PATH}/{agent_id}/reviews", json={"responsibility_confirmed": True})
    assert response.status_code == 201, response.text
    pending = [one for one in versions(response.json()) if one["review_status"] == "pending"]
    assert len(pending) == 1
    return str(pending[0]["review_id"])


def listed(client: TestClient, path: str) -> dict[str, Body]:
    response = client.get(path)
    assert response.status_code == 200, response.text
    rows: list[Body] = response.json()
    return {str(one["id"]): one for one in rows}


def versions(body: Body) -> list[Body]:
    """从响应体里取版本数组。JSON 的值在类型上是不透明的，取出来要当场说清形状。"""
    found = body["versions"]
    assert isinstance(found, list)
    return [one for one in found if isinstance(one, dict)]


def test_a_new_agent_is_private_with_one_draft(client: TestClient) -> None:
    created = create_agent(client)

    assert created["visibility"] == "private"
    assert created["in_catalog"] is False
    assert [(one["version"], one["status"]) for one in versions(created)] == [(1, "draft")]


def test_a_duplicate_name_under_one_author_is_rejected(client: TestClient) -> None:
    name = f"重名-{uuid4().hex[:8]}"
    body = {"name": name, "system_prompt": "x"}
    assert client.post(AGENT_PATH, json=body).status_code == 201

    again = client.post(AGENT_PATH, json=body)

    assert again.status_code == 422
    assert again.json()["error"]["code"] == "VALIDATION_ERROR"


def test_releasing_twice_without_editing_is_rejected(client: TestClient) -> None:
    agent_id = str(create_agent(client)["id"])
    release(client, agent_id)

    assert client.post(f"{AGENT_PATH}/{agent_id}/versions").status_code == 422


def test_editing_after_releasing_appends_a_new_draft(client: TestClient) -> None:
    """已发布的版本一个字都改不动 —— 落进 run 快照的引用要照常读得回来。"""
    agent_id = str(create_agent(client, prompt="喵")["id"])
    release(client, agent_id)

    changed = client.put(f"{AGENT_PATH}/{agent_id}/draft", json={"system_prompt": "汪"})

    assert changed.status_code == 200
    assert [(one["version"], one["status"], one["system_prompt"]) for one in versions(changed.json())] == [
        (1, "released", "喵"),
        (2, "draft", "汪"),
    ]


def test_group_sharing_is_seen_by_the_group_and_not_by_outsiders(
    client: TestClient, group: Group, teammate: User, outsider: User
) -> None:
    """本期第一条主判据。**双向** —— 只断言同组看得见是不够的。"""
    agent_id = str(create_agent(client)["id"])
    release(client, agent_id)
    share(client, agent_id, group)

    as_user(client, teammate)
    assert agent_id in listed(client, f"{AGENT_PATH}/available")
    as_user(client, outsider)
    assert agent_id not in listed(client, f"{AGENT_PATH}/available")


def test_an_outsider_gets_404_not_403_for_someone_elses_agent(client: TestClient, outsider: User) -> None:
    """403 等于确认了「你猜的这个 id 是存在的」，可以拿来把整个库探一遍。"""
    agent_id = str(create_agent(client)["id"])

    as_user(client, outsider)

    assert client.get(f"{AGENT_PATH}/mine/{agent_id}").status_code == 404
    assert client.patch(f"{AGENT_PATH}/{agent_id}", json={"name": "抢过来"}).status_code == 404
    assert client.put(f"{AGENT_PATH}/{agent_id}/draft", json={"system_prompt": "偷改"}).status_code == 404
    assert client.post(f"{AGENT_PATH}/{agent_id}/versions").status_code == 404
    assert client.delete(f"{AGENT_PATH}/{agent_id}").status_code == 404


def test_sharing_with_a_group_i_am_not_in_is_rejected(client: TestClient, platform: Platform, outsider: User) -> None:
    """反向的越权：不是「看见了不该看的」，是「让别人看见了不该看的」。"""
    agent_id = str(create_agent(client)["id"])
    theirs = make_group(client, platform, owner_id=outsider.id)

    response = client.put(f"{AGENT_PATH}/{agent_id}/sharing", json={"visibility": "group", "group_ids": [theirs.id]})

    assert response.status_code == 422


def test_taking_the_sharing_back_removes_it_at_once(
    client: TestClient, author: dict[str, str], group: Group, teammate: User
) -> None:
    agent_id = str(create_agent(client)["id"])
    release(client, agent_id)
    share(client, agent_id, group)
    as_user(client, teammate)
    assert agent_id in listed(client, f"{AGENT_PATH}/available")

    login(client, author["name"])
    client.put(f"{AGENT_PATH}/{agent_id}/sharing", json={"visibility": "private", "group_ids": []})

    login(client, teammate.name)
    assert agent_id not in listed(client, f"{AGENT_PATH}/available")


def test_a_deleted_agent_stays_in_mine_and_leaves_every_other_list(
    client: TestClient, group: Group, teammate: User
) -> None:
    agent_id = str(create_agent(client)["id"])
    release(client, agent_id)
    share(client, agent_id, group)

    assert client.delete(f"{AGENT_PATH}/{agent_id}").status_code == 204

    assert listed(client, f"{AGENT_PATH}/mine")[agent_id]["is_deleted"] is True
    assert agent_id not in listed(client, f"{AGENT_PATH}/available")
    as_user(client, teammate)
    assert agent_id not in listed(client, f"{AGENT_PATH}/available")


def test_submitting_without_confirming_responsibility_is_rejected(client: TestClient) -> None:
    """只靠前端拦的话，直接打接口就绕过了。"""
    agent_id = str(create_agent(client)["id"])
    release(client, agent_id)

    response = client.post(f"{AGENT_PATH}/{agent_id}/reviews", json={"responsibility_confirmed": False})

    assert response.status_code == 422


def test_submitting_before_releasing_is_rejected(client: TestClient) -> None:
    agent_id = str(create_agent(client)["id"])

    response = client.post(f"{AGENT_PATH}/{agent_id}/reviews", json={"responsibility_confirmed": True})

    assert response.status_code == 422


def test_an_unapproved_agent_never_reaches_the_plaza(client: TestClient, reviewer: User, outsider: User) -> None:
    agent_id = str(create_agent(client)["id"])
    release(client, agent_id)
    submit_review(client, agent_id)

    as_user(client, outsider)

    assert agent_id not in listed(client, AGENT_PATH)


def test_a_rejection_reaches_the_author_word_for_word(
    client: TestClient, group: Group, teammate: User, reviewer: User, outsider: User
) -> None:
    """被拒不影响组内：审核管的是别人能不能看见，不是作者能不能用。"""
    agent_id = str(create_agent(client)["id"])
    release(client, agent_id)
    share(client, agent_id, group)
    review_id = submit_review(client, agent_id)

    as_user(client, reviewer)
    decided = client.post(f"{REVIEW_PATH}/{review_id}", json={"approved": False, "reason": "提示词过于宽泛"})
    assert decided.status_code == 202

    as_user(client, outsider)
    assert agent_id not in listed(client, AGENT_PATH)
    as_user(client, teammate)
    assert agent_id in listed(client, f"{AGENT_PATH}/available")


def test_rejecting_without_a_reason_is_rejected(client: TestClient, reviewer: User) -> None:
    """作者看到的不能是「被拒了，没说为什么」。"""
    agent_id = str(create_agent(client)["id"])
    release(client, agent_id)
    review_id = submit_review(client, agent_id)

    as_user(client, reviewer)

    assert client.post(f"{REVIEW_PATH}/{review_id}", json={"approved": False}).status_code == 422
    assert client.post(f"{REVIEW_PATH}/{review_id}", json={"approved": False, "reason": "  "}).status_code == 422


def test_approving_puts_that_version_on_the_plaza(client: TestClient, reviewer: User, outsider: User) -> None:
    agent_id = str(create_agent(client, prompt="第一版")["id"])
    release(client, agent_id)
    review_id = submit_review(client, agent_id)

    as_user(client, reviewer)
    assert client.post(f"{REVIEW_PATH}/{review_id}", json={"approved": True}).status_code == 202

    as_user(client, outsider)
    plaza = listed(client, AGENT_PATH)
    assert plaza[agent_id]["version"] == 1
    assert plaza[agent_id]["system_prompt"] == "第一版"
    assert plaza[agent_id]["source"] == "catalog"


def test_public_catalog_is_anonymous_and_redacted(client: TestClient, reviewer: User) -> None:
    """落地页市场区是匿名入口（审查文档 D1 决策 A），但投影必须删掉敏感字段。

    匿名拿得到目录（与广场同一份数据），拿不到提示词全文、MCP 引用与 owner_id ——
    这三样属于登录后的可见性语境。顺带钉死边界：**别的 agent 端点仍要登录**，
    匿名能读的只有这一个投影。
    """
    agent_id = str(create_agent(client, prompt=CAT_PROMPT)["id"])
    release(client, agent_id)
    review_id = submit_review(client, agent_id)
    as_user(client, reviewer)
    assert client.post(f"{REVIEW_PATH}/{review_id}", json={"approved": True}).status_code == 202

    client.cookies.clear()
    assert client.get(AGENT_PATH).status_code == 401

    response = client.get(f"{AGENT_PATH}/public")
    assert response.status_code == 200
    body = response.json()
    # 目录是会话级累积的（同库跑的别的用例也在里面），按成员关系断言
    ids = [one["id"] for one in body]
    assert agent_id in ids
    one = next(item for item in body if item["id"] == agent_id)
    for key in ("system_prompt", "mcp_refs", "owner_id", "source", "visibility"):
        assert key not in one, f"匿名投影泄露了 {key}"


def test_an_unapproved_agent_never_reaches_the_public_catalog(client: TestClient) -> None:
    """公开目录与广场同口径：没审过的版本不该出现在落地页上。"""
    agent_id = str(create_agent(client, prompt=CAT_PROMPT)["id"])

    client.cookies.clear()
    response = client.get(f"{AGENT_PATH}/public")
    assert response.status_code == 200
    assert agent_id not in [one["id"] for one in response.json()]


def test_editing_after_approval_does_not_slip_onto_the_plaza(
    client: TestClient, author: dict[str, str], reviewer: User, outsider: User
) -> None:
    """审核真的拦住每一次变更。少了这一条，「审一次之后随便改」的实现照样全绿。"""
    agent_id = str(create_agent(client, prompt="第一版")["id"])
    release(client, agent_id)
    review_id = submit_review(client, agent_id)
    as_user(client, reviewer)
    client.post(f"{REVIEW_PATH}/{review_id}", json={"approved": True})

    login(client, author["name"])
    client.put(f"{AGENT_PATH}/{agent_id}/draft", json={"system_prompt": "第二版"})
    release(client, agent_id)
    submit_review(client, agent_id)

    as_user(client, outsider)
    plaza = listed(client, AGENT_PATH)
    assert (plaza[agent_id]["version"], plaza[agent_id]["system_prompt"]) == (1, "第一版")


def test_a_reviewer_may_review_and_may_not_manage_accounts(client: TestClient, reviewer: User) -> None:
    """`reviewer` 的边界。一旦让它顺手多拿一样，这个角色就退化成 `admin` 的别名。"""
    as_user(client, reviewer)

    assert client.get(REVIEW_PATH).status_code == 200
    assert (
        client.post("/api/admin/users", json={"name": "新号", "password": "口令-test", "role": "teacher"}).status_code
        == 403
    )
    assert client.patch(f"/api/admin/users/{uuid4().hex}", json={"is_active": False}).status_code == 403
    assert client.get("/api/admin/users").status_code == 403


def test_a_teacher_cannot_open_the_review_queue(client: TestClient) -> None:
    """这里给 403 而不是 404：「你的角色不够」不泄露任何东西。"""
    response = client.get(REVIEW_PATH)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_an_admin_satisfies_reviewer_too(client: TestClient, platform: Platform, hasher: PasswordHasher) -> None:
    """反过来不成立 —— 多给管理员一样能力不改变任何边界，他本来就能改任何账号的角色。"""
    boss = signup(client, platform, hasher, name=f"admin-{uuid4().hex[:8]}", role=UserRole.ADMIN)

    as_user(client, boss)

    assert client.get(REVIEW_PATH).status_code == 200


def test_referencing_an_agent_freezes_its_prompt_into_the_run_snapshot(client: TestClient, thread_id: str) -> None:
    """只看输出的话分不清是引用生效了还是模型碰巧这么答的 —— 快照里三样都要有。"""
    agent_id = str(create_agent(client, prompt=CAT_PROMPT)["id"])
    release(client, agent_id)

    response = client.post(
        f"/api/threads/{thread_id}/runs",
        json={"content": "算个波动率", "agent_config": {"agent_id": agent_id}},
    )

    assert response.status_code == 202, response.text
    assert response.json()["agent_config"] == {
        "system_prompt": CAT_PROMPT,
        "agent_id": agent_id,
        "agent_version": 1,
    }


def test_an_agent_carries_its_frozen_skills_into_a_run(client: TestClient, thread_id: str) -> None:
    skill_id = create_skill(client, f"annualized-{uuid4().hex[:8]}")
    response = client.post(
        AGENT_PATH,
        json={
            "name": f"带能力智能体-{uuid4().hex[:8]}",
            "system_prompt": "按能力说明工作",
            "skills": [skill_id],
        },
    )
    assert response.status_code == 201, response.text
    agent_id = str(response.json()["id"])
    released = release(client, agent_id)
    frozen = versions(released)[0]["skill_refs"]

    run = client.post(
        f"/api/threads/{thread_id}/runs",
        json={"content": "算年化收益", "agent_config": {"agent_id": agent_id}},
    )

    assert run.status_code == 202, run.text
    assert run.json()["agent_config"]["skills"] == frozen


def test_an_agent_carries_its_frozen_subagents_into_a_run(client: TestClient, thread_id: str) -> None:
    child = create_agent(client, prompt="只做波动率")
    child_id = str(child["id"])
    child_name = str(child["name"])
    release(client, child_id)

    run = client.post(
        f"/api/threads/{thread_id}/runs",
        json={"content": "算年化收益", "agent_config": {"subagents": [child_id]}},
    )

    assert run.status_code == 202, run.text
    refs = run.json()["agent_config"]["subagents"]
    assert refs == [{"agent_id": child_id, "version": 1, "name": child_name}]
    assert listed(client, f"{AGENT_PATH}/mine")[child_id]["call_count"] == 1


def test_a_scene_agent_is_available_but_not_a_subagent_candidate(client: TestClient) -> None:
    child_id = str(create_agent(client, prompt="只做波动率")["id"])
    release(client, child_id)

    scene = client.post(
        AGENT_PATH,
        json={
            "name": f"场景-{uuid4().hex[:8]}",
            "system_prompt": "负责调度",
            "subagents": [child_id],
        },
    )
    assert scene.status_code == 201, scene.text
    scene_id = str(scene.json()["id"])
    release(client, scene_id)

    assert scene_id in listed(client, f"{AGENT_PATH}/available")
    assert scene_id not in listed(client, f"{AGENT_PATH}/subagent-candidates")
    assert child_id in listed(client, f"{AGENT_PATH}/subagent-candidates")


def test_a_scene_agent_cannot_be_attached_as_a_temporary_subagent(client: TestClient, thread_id: str) -> None:
    child_id = str(create_agent(client, prompt="只做波动率")["id"])
    release(client, child_id)
    scene = client.post(
        AGENT_PATH,
        json={
            "name": f"场景-{uuid4().hex[:8]}",
            "system_prompt": "负责调度",
            "subagents": [child_id],
        },
    )
    assert scene.status_code == 201, scene.text
    scene_id = str(scene.json()["id"])
    release(client, scene_id)

    response = client.post(
        f"/api/threads/{thread_id}/runs",
        json={"content": "一", "agent_config": {"subagents": [scene_id]}},
    )

    assert response.status_code == 422
    assert "已挂子智能体" in response.json()["error"]["message"]
    assert client.get(f"/api/threads/{thread_id}/runs").json()["items"] == []


def test_more_than_five_subagents_are_rejected_before_resolution(client: TestClient, thread_id: str) -> None:
    response = client.post(
        f"/api/threads/{thread_id}/runs",
        json={"content": "太多子智能体", "agent_config": {"subagents": [uuid4().hex for _ in range(6)]}},
    )

    assert response.status_code == 422
    assert "5" in response.json()["error"]["message"]
    assert client.get(f"/api/threads/{thread_id}/runs").json()["items"] == []


def test_a_reference_counts_as_one_call(client: TestClient, thread_id: str) -> None:
    agent_id = str(create_agent(client)["id"])
    release(client, agent_id)

    client.post(f"/api/threads/{thread_id}/runs", json={"content": "一", "agent_config": {"agent_id": agent_id}})

    assert listed(client, f"{AGENT_PATH}/mine")[agent_id]["call_count"] == 1


def test_picking_an_agent_and_writing_a_prompt_at_once_is_rejected(client: TestClient, thread_id: str) -> None:
    agent_id = str(create_agent(client)["id"])
    release(client, agent_id)

    response = client.post(
        f"/api/threads/{thread_id}/runs",
        json={"content": "一", "agent_config": {"agent_id": agent_id, "system_prompt": "自己写的"}},
    )

    assert response.status_code == 422


def test_an_outsider_cannot_reference_an_agent_it_cannot_see(
    client: TestClient, group: Group, outsider: User, platform: Platform
) -> None:
    """列表过滤对了而提交侧忘了查，是最典型的漏洞形状。**这一条单独断言。**"""
    agent_id = str(create_agent(client)["id"])
    release(client, agent_id)
    share(client, agent_id, group)

    as_user(client, outsider)
    thread_id = client.post("/api/threads").json()["id"]
    response = client.post(
        f"/api/threads/{thread_id}/runs",
        json={"content": "一", "agent_config": {"agent_id": agent_id}},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert client.get(f"/api/threads/{thread_id}/runs").json()["items"] == []


def test_a_withdrawn_reference_fails_loudly_instead_of_falling_back(
    client: TestClient, author: dict[str, str], group: Group, teammate: User
) -> None:
    """静默回退跑得完、不报错，唯一的症状是回答变了味。判据必须把这两者分开。"""
    agent_id = str(create_agent(client)["id"])
    release(client, agent_id)
    share(client, agent_id, group)

    as_user(client, teammate)
    thread_id = client.post("/api/threads").json()["id"]
    # 会话默认里存着这个引用，之后每一轮都按它去解析
    assert client.patch(f"/api/threads/{thread_id}", json={"agent_config": {"agent_id": agent_id}}).status_code == 200

    login(client, author["name"])
    client.put(f"{AGENT_PATH}/{agent_id}/sharing", json={"visibility": "private", "group_ids": []})

    login(client, teammate.name)
    response = client.post(f"/api/threads/{thread_id}/runs", json={"content": "一"})

    assert response.status_code == 422
    assert client.get(f"/api/threads/{thread_id}/runs").json()["items"] == []


def test_referencing_an_unknown_agent_is_rejected(client: TestClient, thread_id: str) -> None:
    response = client.post(
        f"/api/threads/{thread_id}/runs",
        json={"content": "一", "agent_config": {"agent_id": uuid4().hex}},
    )

    assert response.status_code == 422


def test_an_unreferenced_run_carries_no_extra_key(client: TestClient, thread_id: str) -> None:
    """不选 agent 时快照里一个键都不多 —— 历史判据断言的正是「快照 == 当时那份配置」。"""
    response = client.post(f"/api/threads/{thread_id}/runs", json={"content": "一"})

    assert response.json()["agent_config"] == {}
