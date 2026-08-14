"""Skill 目录端点：上传、版本、可见性与审核。"""

from functools import partial
from io import BytesIO
from pathlib import Path
from typing import cast
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from fastapi.testclient import TestClient
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from api.platform import Platform
from auth.password import PasswordHasher
from group.repository import Group
from preset.model import ResourceKind, ReviewRecord
from test.api.agent_test import as_user, create_agent
from test.api.agent_test import release as release_agent
from test.api.agent_test import submit_review as submit_agent_review
from test.api.conftest import login, make_group, signup
from user.model import UserRole
from user.repository import User

SKILL_PATH = "/api/skills"
REVIEW_PATH = "/api/reviews"


def markdown(name: str, description: str = "统一年化口径") -> bytes:
    return f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n".encode()


def zipped(name: str, *, skill_name: str | None = None, extra: dict[str, bytes] | None = None) -> bytes:
    stream = BytesIO()
    with ZipFile(stream, "w", ZIP_DEFLATED) as archive:
        archive.writestr(f"{name}/SKILL.md", markdown(skill_name or name))
        for path, content in (extra or {}).items():
            archive.writestr(f"{name}/{path}", content)
    return stream.getvalue()


def create_skill(client: TestClient, name: str | None = None, *, subject: str = "金融学") -> dict[str, object]:
    actual = name or f"annualized-{uuid4().hex[:8]}"
    response = client.post(
        SKILL_PATH,
        data={"subject": subject},
        files={"file": (f"{actual}.md", markdown(actual), "text/markdown")},
    )
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    return body


def release(client: TestClient, skill_id: str) -> dict[str, object]:
    response = client.post(f"{SKILL_PATH}/{skill_id}/versions")
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    return body


def submit_review(client: TestClient, skill_id: str) -> str:
    response = client.post(f"{SKILL_PATH}/{skill_id}/reviews", json={"responsibility_confirmed": True})
    assert response.status_code == 201, response.text
    versions = response.json()["versions"]
    pending = [one for one in versions if one["review_status"] == "pending"]
    assert len(pending) == 1
    return str(pending[0]["review_id"])


def listed(client: TestClient, path: str) -> dict[str, dict[str, object]]:
    response = client.get(path)
    assert response.status_code == 200, response.text
    return {str(one["id"]): one for one in response.json()}


@pytest.fixture
def author(client: TestClient) -> dict[str, str]:
    body: dict[str, str] = client.get("/api/auth/me").json()
    return body


@pytest.fixture
def group(client: TestClient, platform: Platform, author: dict[str, str]) -> Group:
    return make_group(client, platform, owner_id=author["id"])


@pytest.fixture
def teammate(client: TestClient, platform: Platform, hasher: PasswordHasher, group: Group) -> User:
    member = signup(client, platform, hasher, name=f"同组-skill-{uuid4().hex[:8]}")
    assert client.portal is not None
    client.portal.call(partial(platform.group.add_member, group_id=group.id, user_id=member.id))
    return member


@pytest.fixture
def outsider(client: TestClient, platform: Platform, hasher: PasswordHasher) -> User:
    stranger = signup(client, platform, hasher, name=f"别组-skill-{uuid4().hex[:8]}")
    make_group(client, platform, owner_id=stranger.id)
    return stranger


@pytest.fixture
def reviewer(client: TestClient, platform: Platform, hasher: PasswordHasher) -> User:
    return signup(client, platform, hasher, name=f"审核-skill-{uuid4().hex[:8]}", role=UserRole.REVIEWER)


def test_a_single_markdown_upload_creates_v1_and_persists_clean_bytes(client: TestClient, tmp_path: Path) -> None:
    created = create_skill(client)
    skill_id = str(created["id"])
    name = str(created["name"])

    assert created["visibility"] == "private"
    versions = cast(list[dict[str, object]], created["versions"])
    assert [(one["version"], one["status"]) for one in versions] == [(1, "draft")]
    assert (tmp_path / "skill" / skill_id / "1" / "SKILL.md").read_bytes() == markdown(name)


def test_a_zip_upload_uses_frontmatter_and_keeps_every_valid_file(client: TestClient, tmp_path: Path) -> None:
    name = f"zip-skill-{uuid4().hex[:8]}"
    response = client.post(
        SKILL_PATH,
        data={"subject": "计量经济学"},
        files={"file": (f"{name}.zip", zipped(name, extra={"notes/rule.txt": b"252"}), "application/zip")},
    )

    assert response.status_code == 201, response.text
    created = response.json()
    root = tmp_path / "skill" / created["id"] / "1"
    assert created["name"] == name
    assert created["versions"][0]["file_count"] == 2
    assert (root / "notes" / "rule.txt").read_bytes() == b"252"


def test_validation_reasons_reach_the_api_and_leave_no_database_or_disk_residue(
    client: TestClient, tmp_path: Path
) -> None:
    before = set(listed(client, f"{SKILL_PATH}/mine"))
    stream = BytesIO()
    with ZipFile(stream, "w") as archive:
        archive.writestr("../escape.py", b"x")
        archive.writestr("bad.exe", b"x")

    response = client.post(
        SKILL_PATH,
        files={"file": ("hostile.zip", stream.getvalue(), "application/zip")},
    )

    assert response.status_code == 422
    message = response.json()["error"]["message"]
    assert "路径不合法" in message
    assert "文件扩展名不允许" in message
    assert set(listed(client, f"{SKILL_PATH}/mine")) == before
    assert not (tmp_path / "skill").exists()


def test_a_later_version_cannot_rename_the_skill(client: TestClient, tmp_path: Path) -> None:
    created = create_skill(client)
    skill_id = str(created["id"])
    release(client, skill_id)
    renamed = f"renamed-{uuid4().hex[:8]}"

    response = client.post(
        f"{SKILL_PATH}/{skill_id}/draft",
        files={"file": (f"{renamed}.md", markdown(renamed), "text/markdown")},
    )

    assert response.status_code == 422
    assert "改名请新建一个 Skill" in response.json()["error"]["message"]
    assert not (tmp_path / "skill" / skill_id / "2").exists()


def test_group_sharing_is_visible_only_to_members(
    client: TestClient, group: Group, teammate: User, outsider: User
) -> None:
    created = create_skill(client)
    skill_id = str(created["id"])
    release(client, skill_id)
    response = client.put(
        f"{SKILL_PATH}/{skill_id}/sharing",
        json={"visibility": "group", "group_ids": [group.id]},
    )
    assert response.status_code == 200, response.text

    as_user(client, teammate)
    assert skill_id in listed(client, f"{SKILL_PATH}/available")
    as_user(client, outsider)
    assert skill_id not in listed(client, f"{SKILL_PATH}/available")
    assert skill_id not in listed(client, SKILL_PATH)


def test_rejection_does_not_break_group_use_and_approval_puts_skill_in_catalog(
    client: TestClient, group: Group, teammate: User, outsider: User, reviewer: User
) -> None:
    created = create_skill(client)
    skill_id = str(created["id"])
    release(client, skill_id)
    assert (
        client.put(
            f"{SKILL_PATH}/{skill_id}/sharing",
            json={"visibility": "group", "group_ids": [group.id]},
        ).status_code
        == 200
    )
    review_id = submit_review(client, skill_id)

    as_user(client, reviewer)
    rejected = client.post(f"{REVIEW_PATH}/{review_id}", json={"approved": False, "reason": "说明不够清楚"})
    assert rejected.status_code == 202, rejected.text
    assert rejected.json()["target_kind"] == "skill"

    as_user(client, teammate)
    assert skill_id in listed(client, f"{SKILL_PATH}/available")
    as_user(client, outsider)
    assert skill_id not in listed(client, SKILL_PATH)

    # 被拒的同一版本允许重新提审。
    client.cookies.clear()
    login(client, str(created["owner_name"]))
    second = submit_review(client, skill_id)
    as_user(client, reviewer)
    assert client.post(f"{REVIEW_PATH}/{second}", json={"approved": True}).status_code == 202
    as_user(client, outsider)
    assert skill_id in listed(client, SKILL_PATH)
    assert skill_id in listed(client, f"{SKILL_PATH}/available")


def test_soft_delete_keeps_mine_but_removes_every_other_visibility(
    client: TestClient, group: Group, teammate: User
) -> None:
    created = create_skill(client)
    skill_id = str(created["id"])
    release(client, skill_id)
    assert (
        client.put(
            f"{SKILL_PATH}/{skill_id}/sharing",
            json={"visibility": "group", "group_ids": [group.id]},
        ).status_code
        == 200
    )

    assert client.delete(f"{SKILL_PATH}/{skill_id}").status_code == 204
    assert listed(client, f"{SKILL_PATH}/mine")[skill_id]["is_deleted"] is True
    as_user(client, teammate)
    assert skill_id not in listed(client, f"{SKILL_PATH}/available")


def test_reviews_table_can_hold_agent_and_skill_targets_together(client: TestClient, platform: Platform) -> None:
    agent = create_agent(client)
    release_agent(client, str(agent["id"]))
    submit_agent_review(client, str(agent["id"]))
    skill = create_skill(client)
    release(client, str(skill["id"]))
    submit_review(client, str(skill["id"]))

    async def target_kinds() -> set[ResourceKind]:
        async with AsyncSession(platform.engine) as session:
            found = await session.exec(select(col(ReviewRecord.target_kind)))
            return set(found.all())

    assert client.portal is not None
    assert {ResourceKind.AGENT, ResourceKind.SKILL} <= client.portal.call(target_kinds)
