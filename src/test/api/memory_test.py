"""教师管理当前 thread 记忆的 API 测试。"""

from functools import partial
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.platform import Platform
from app.auth.password import PasswordHasher
from app.memory.store import MemoryRecord, MemoryStore
from app.sandbox.workspace import Workspace
from app.user.model import UserRole
from test.api.conftest import login, signup


@pytest.fixture
def stored_memory(thread_id: str, memory_store: MemoryStore) -> MemoryRecord:
    """在当前教师的 thread 中写一条可管理的记忆。"""
    return memory_store.write(
        thread_id,
        MemoryRecord(
            slug="risk-preference",
            name="风险偏好",
            description="教师偏好用中性风险假设",
            type="user",
            content="默认采用中性风险情景，并单列压力测试。",
        ),
    )


def test_memory_list_returns_only_catalog_fields(
    client: TestClient,
    thread_id: str,
    stored_memory: MemoryRecord,
) -> None:
    """列表可审计但不提前泄露正文。"""
    response = client.get(f"/api/threads/{thread_id}/memories")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item == {
        "slug": stored_memory.slug,
        "name": stored_memory.name,
        "description": stored_memory.description,
        "type": stored_memory.type,
        "updated_at": item["updated_at"],
    }
    assert item["updated_at"]
    assert "content" not in item
    assert "body" not in item


def test_an_empty_memory_catalog_is_an_empty_list(client: TestClient, thread_id: str) -> None:
    response = client.get(f"/api/threads/{thread_id}/memories")

    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_memory_detail_renames_internal_body_to_content(
    client: TestClient,
    thread_id: str,
    stored_memory: MemoryRecord,
) -> None:
    response = client.get(f"/api/threads/{thread_id}/memories/{stored_memory.slug}")

    assert response.status_code == 200
    assert response.json() == {
        "slug": stored_memory.slug,
        "name": stored_memory.name,
        "description": stored_memory.description,
        "type": stored_memory.type,
        "updated_at": response.json()["updated_at"],
        "content": stored_memory.content,
    }
    assert response.json()["updated_at"]
    assert "body" not in response.json()


def test_deleting_memory_physically_removes_it_from_list_and_detail(
    client: TestClient,
    thread_id: str,
    stored_memory: MemoryRecord,
    memory_store: MemoryStore,
) -> None:
    response = client.delete(f"/api/threads/{thread_id}/memories/{stored_memory.slug}")

    assert response.status_code == 204
    assert client.get(f"/api/threads/{thread_id}/memories").json() == {"items": []}
    assert client.get(f"/api/threads/{thread_id}/memories/{stored_memory.slug}").status_code == 404
    with pytest.raises(FileNotFoundError):
        memory_store.read(thread_id, stored_memory.slug)


@pytest.mark.parametrize(
    ("method", "suffix"),
    [
        ("get", ""),
        ("get", "/risk-preference"),
        ("delete", "/risk-preference"),
    ],
)
@pytest.mark.parametrize("role", [UserRole.TEACHER, UserRole.ADMIN])
def test_another_user_and_admin_get_404_before_reaching_memory(
    client: TestClient,
    platform: Platform,
    hasher: PasswordHasher,
    thread_id: str,
    stored_memory: MemoryRecord,
    memory_store: MemoryStore,
    method: str,
    suffix: str,
    role: UserRole,
) -> None:
    """管理员也不能借管理身份查看或删除他人的 thread 正文。"""
    name = f"{role.value}-{uuid4().hex[:8]}"
    signup(client, platform, hasher, name=name, role=role)
    client.cookies.clear()
    login(client, name)

    response = client.request(method, f"/api/threads/{thread_id}/memories{suffix}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
    assert memory_store.read(thread_id, stored_memory.slug).content == stored_memory.content


def test_a_deleted_thread_is_404_even_while_its_memory_still_exists(
    client: TestClient,
    platform: Platform,
    thread_id: str,
    stored_memory: MemoryRecord,
    memory_store: MemoryStore,
) -> None:
    """Active thread 由数据库判定，不能拿尚未清掉的目录当存在性权威。"""
    owner_id = client.get("/api/auth/me").json()["id"]
    assert client.portal is not None
    client.portal.call(partial(platform.thread.delete, thread_id, user_id=owner_id))

    response = client.get(f"/api/threads/{thread_id}/memories")

    assert response.status_code == 404
    assert memory_store.read(thread_id, stored_memory.slug).content == stored_memory.content


@pytest.mark.parametrize("slug", ["../secret", "UPPER", "two--dash"])
def test_an_invalid_memory_slug_is_not_found(client: TestClient, thread_id: str, slug: str) -> None:
    response = client.get(f"/api/threads/{thread_id}/memories/{slug}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.parametrize("method", ["get", "delete"])
def test_a_missing_memory_is_not_found(client: TestClient, thread_id: str, method: str) -> None:
    response = client.request(method, f"/api/threads/{thread_id}/memories/not-created")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_an_active_database_thread_with_a_missing_workspace_is_not_found(
    client: TestClient,
    thread_id: str,
    space: Workspace,
) -> None:
    """Broker 物理资源缺失不能伪装成空 catalog。"""
    space.destroy(thread_id)

    response = client.get(f"/api/threads/{thread_id}/memories")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.parametrize(
    ("method", "suffix"),
    [("post", ""), ("put", "/manual")],
)
def test_memory_has_no_manual_write_endpoint(
    client: TestClient,
    thread_id: str,
    method: str,
    suffix: str,
) -> None:
    response = client.request(
        method,
        f"/api/threads/{thread_id}/memories{suffix}",
        json={
            "slug": "manual",
            "name": "手工记忆",
            "description": "不该写入",
            "type": "user",
            "content": "不该写入",
        },
    )

    assert response.status_code == 405
