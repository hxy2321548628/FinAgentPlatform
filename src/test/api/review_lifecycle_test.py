"""审核详情与平台目录上下架端点。"""

from functools import partial
from io import BytesIO
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi.testclient import TestClient

from app.api.platform import Platform
from app.auth.password import PasswordHasher
from app.group.repository import Group
from app.user.model import UserRole
from app.user.repository import User
from test.api.agent_test import create_agent, listed, release, share, submit_review
from test.api.conftest import login, make_group, signup
from test.api.skill_test import create_skill, markdown
from test.api.skill_test import release as release_skill
from test.api.skill_test import submit_review as submit_skill_review

REVIEW_PATH = "/api/reviews"


def reviewer(client: TestClient, platform: Platform, hasher: PasswordHasher) -> User:
    """建立一个审核员。"""
    return signup(client, platform, hasher, name=f"审核详情-{uuid4().hex[:8]}", role=UserRole.REVIEWER)


def approve(client: TestClient, review_id: str) -> None:
    """通过一条待审记录。"""
    response = client.post(f"{REVIEW_PATH}/{review_id}", json={"approved": True})
    assert response.status_code == 202, response.text


def switch_to(client: TestClient, name: str) -> None:
    """切换当前登录身份。"""
    client.cookies.clear()
    login(client, name)


def test_reviewer_can_read_frozen_agent_detail_but_cannot_take_it_down(
    client: TestClient,
    platform: Platform,
    hasher: PasswordHasher,
    admin: str,
) -> None:
    """详情属于审核权，下架属于管理权。"""
    ability = create_skill(client)
    ability_id = str(ability["id"])
    release_skill(client, ability_id)
    child = create_agent(client, prompt="子智能体提示词")
    child_id = str(child["id"])
    release(client, child_id)
    response = client.post(
        "/api/agents",
        json={
            "name": f"冻结场景-{uuid4().hex[:8]}",
            "description": "冻结完整编排",
            "subject": "金融学",
            "system_prompt": "冻结的系统提示词",
            "skills": [ability_id],
            "subagents": [child_id],
        },
    )
    assert response.status_code == 201, response.text
    created = response.json()
    agent_id = str(created["id"])
    release(client, agent_id)
    review_id = submit_review(client, agent_id)
    assert client.get(f"{REVIEW_PATH}/{review_id}").status_code == 403
    account = reviewer(client, platform, hasher)
    switch_to(client, account.name)

    detail = client.get(f"{REVIEW_PATH}/{review_id}")
    forbidden = client.post(
        f"{REVIEW_PATH}/{review_id}/catalog",
        json={"enabled": False, "reason": "内容已过期"},
    )

    assert detail.status_code == 200, detail.text
    assert detail.json()["system_prompt"] == "冻结的系统提示词"
    assert detail.json()["skill_refs"] == [{"skill_id": ability_id, "version": 1, "name": ability["name"]}]
    assert detail.json()["subagent_refs"] == [{"agent_id": child_id, "version": 1, "name": child["name"]}]
    assert detail.json()["mcp_refs"] is None
    assert detail.json()["catalog_enabled"] is True
    assert forbidden.status_code == 403, forbidden.text

    switch_to(client, admin)
    pending_toggle = client.post(
        f"{REVIEW_PATH}/{review_id}/catalog",
        json={"enabled": False, "reason": "尝试越过审核"},
    )
    assert pending_toggle.status_code == 422, pending_toggle.text
    assert client.post(f"{REVIEW_PATH}/{review_id}", json={"approved": True}).status_code == 202


def test_admin_take_down_is_resource_wide_and_keeps_owner_and_group_access(
    client: TestClient,
    admin: str,
    platform: Platform,
    hasher: PasswordHasher,
) -> None:
    """下架不得回退到旧过审版，也不得伤及作者与组内可见性。"""
    author: dict[str, str] = client.get("/api/auth/me").json()
    group: Group = make_group(client, platform, owner_id=author["id"])
    teammate = signup(client, platform, hasher, name=f"同组下架-{uuid4().hex[:8]}")
    outsider = signup(client, platform, hasher, name=f"别组下架-{uuid4().hex[:8]}")
    assert client.portal is not None
    client.portal.call(partial(platform.group.add_member, group_id=group.id, user_id=teammate.id))
    created = create_agent(client, prompt="第一版")
    agent_id = str(created["id"])
    release(client, agent_id)
    share(client, agent_id, group)
    first_review = submit_review(client, agent_id)
    switch_to(client, admin)
    approve(client, first_review)

    switch_to(client, author["name"])
    changed = client.put(
        f"/api/agents/{agent_id}/draft",
        json={"system_prompt": "第二版", "skills": [], "subagents": [], "mcps": []},
    )
    assert changed.status_code == 200, changed.text
    release(client, agent_id)
    second_review = submit_review(client, agent_id)
    switch_to(client, admin)
    approve(client, second_review)

    blank = client.post(f"{REVIEW_PATH}/{second_review}/catalog", json={"enabled": False, "reason": "  "})
    stopped = client.post(
        f"{REVIEW_PATH}/{second_review}/catalog",
        json={"enabled": False, "reason": "规则变更，暂停对外开放"},
    )

    assert blank.status_code == 422, blank.text
    assert stopped.status_code == 202, stopped.text
    assert stopped.json()["status"] == "approved"
    assert stopped.json()["catalog_enabled"] is False
    assert stopped.json()["catalog_disabled_reason"] == "规则变更，暂停对外开放"
    assert stopped.json()["catalog_disabled_by"] == client.get("/api/auth/me").json()["id"]
    assert stopped.json()["catalog_disabled_at"] is not None

    switch_to(client, outsider.name)
    assert agent_id not in listed(client, "/api/agents")
    assert agent_id not in listed(client, "/api/agents/available")
    assert agent_id not in [one["id"] for one in client.get("/api/agents/public").json()]
    thread_id = str(client.post("/api/threads").json()["id"])
    refused = client.post(
        f"/api/threads/{thread_id}/runs",
        json={"content": "不能引用已下架智能体", "agent_config": {"agent_id": agent_id}},
    )
    assert refused.status_code == 422, refused.text

    switch_to(client, teammate.name)
    assert listed(client, "/api/agents/available")[agent_id]["source"] == "group"

    switch_to(client, author["name"])
    mine = listed(client, "/api/agents/mine")[agent_id]
    assert mine["in_catalog"] is False
    assert mine["catalog_enabled"] is False
    assert mine["catalog_disabled_reason"] == "规则变更，暂停对外开放"

    switch_to(client, admin)
    restored = client.post(f"{REVIEW_PATH}/{second_review}/catalog", json={"enabled": True})
    assert restored.status_code == 202, restored.text
    assert restored.json()["catalog_disabled_reason"] is None
    assert restored.json()["catalog_disabled_by"] is None
    assert restored.json()["catalog_disabled_at"] is None
    switch_to(client, outsider.name)
    assert listed(client, "/api/agents")[agent_id]["version"] == 2


def test_reviewer_can_browse_pending_skill_files(
    client: TestClient,
    platform: Platform,
    hasher: PasswordHasher,
) -> None:
    """审核员不必先获得 Skill 共享权才能查看待审文件。"""
    name = f"review-files-{uuid4().hex[:8]}"
    stream = BytesIO()
    with ZipFile(stream, "w", ZIP_DEFLATED) as archive:
        archive.writestr(f"{name}/SKILL.md", markdown(name))
        archive.writestr(f"{name}/notes/rule.txt", "252 个交易日".encode())
    response = client.post(
        "/api/skills",
        files={"file": (f"{name}.zip", stream.getvalue(), "application/zip")},
    )
    assert response.status_code == 201, response.text
    skill_id = str(response.json()["id"])
    release_skill(client, skill_id)
    review_id = submit_skill_review(client, skill_id)
    account = reviewer(client, platform, hasher)
    switch_to(client, account.name)

    detail = client.get(f"{REVIEW_PATH}/{review_id}")
    files = client.get(f"{REVIEW_PATH}/{review_id}/files")
    content = client.get(f"{REVIEW_PATH}/{review_id}/files/content", params={"path": "notes/rule.txt"})
    escaped = client.get(f"{REVIEW_PATH}/{review_id}/files/content", params={"path": "../outside.txt"})

    assert detail.status_code == 200, detail.text
    assert detail.json()["skill_id"] == skill_id
    assert files.status_code == 200, files.text
    assert files.json() == [
        {"path": "SKILL.md", "size": len(markdown(name))},
        {"path": "notes/rule.txt", "size": len("252 个交易日".encode())},
    ]
    assert content.status_code == 200, content.text
    assert content.json()["content"] == "252 个交易日"
    assert escaped.status_code == 422, escaped.text


def test_admin_can_take_down_and_restore_an_approved_skill(
    client: TestClient,
    admin: str,
    platform: Platform,
    hasher: PasswordHasher,
) -> None:
    """Skill 下架后仅从平台目录消失，审核历史仍是 approved。"""
    author: dict[str, str] = client.get("/api/auth/me").json()
    outsider = signup(client, platform, hasher, name=f"别组-Skill-{uuid4().hex[:8]}")
    created = create_skill(client)
    skill_id = str(created["id"])
    release_skill(client, skill_id)
    review_id = submit_skill_review(client, skill_id)
    switch_to(client, admin)
    approve(client, review_id)

    stopped = client.post(
        f"{REVIEW_PATH}/{review_id}/catalog",
        json={"enabled": False, "reason": "能力口径已过期"},
    )
    assert stopped.status_code == 202, stopped.text
    assert stopped.json()["status"] == "approved"

    switch_to(client, outsider.name)
    assert skill_id not in listed(client, "/api/skills")
    assert skill_id not in listed(client, "/api/skills/available")
    thread_id = str(client.post("/api/threads").json()["id"])
    refused = client.post(
        f"/api/threads/{thread_id}/runs",
        json={"content": "不能引用已下架 Skill", "agent_config": {"skills": [skill_id]}},
    )
    assert refused.status_code == 422, refused.text

    switch_to(client, author["name"])
    mine = listed(client, "/api/skills/mine")[skill_id]
    assert mine["catalog_enabled"] is False
    assert mine["catalog_disabled_reason"] == "能力口径已过期"

    switch_to(client, admin)
    restored = client.post(f"{REVIEW_PATH}/{review_id}/catalog", json={"enabled": True})
    assert restored.status_code == 202, restored.text
