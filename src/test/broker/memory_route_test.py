import asyncio
from collections.abc import AsyncGenerator, AsyncIterator, Callable
from pathlib import Path
from typing import cast

import httpx
import pytest

from app.broker.app import create_app
from app.broker.route import _acquire_stream, destroy_thread
from app.broker.runtime import Broker, get_broker
from app.broker.skill import SkillStore
from app.memory.model import MemoryServiceProtocol, MemoryType
from app.memory.store import MemoryCapacityError, MemoryStore, MemoryVersionConflictError
from app.memory.store import MemoryRecord as StoredMemoryRecord
from app.sandbox.path import MEMORY_DIR
from app.sandbox.remote import BrokerConnection, FileMissingError, RemoteMemory
from app.sandbox.workspace import Workspace

THREAD_ID = "thread-1"


class FakePool:
    """记忆路由不需要容器；这里只满足 Broker 的装配形状。"""

    def current(self, thread_id: str) -> None:
        del thread_id
        return None


class BlockingDestroyPool(FakePool):
    """让 destroy 停在 discard 中间，复现 acquire 穿透窗口。"""

    def __init__(self, space: Workspace) -> None:
        self._space = space
        self.discard_started = asyncio.Event()
        self.finish_discard = asyncio.Event()
        self.acquire_started = asyncio.Event()

    async def discard(self, thread_id: str) -> None:
        del thread_id
        self.discard_started.set()
        await self.finish_discard.wait()

    async def acquire(
        self,
        thread_id: str,
        *,
        holder: str,
        on_queued: Callable[[int], None],
    ) -> None:
        del holder, on_queued
        self.acquire_started.set()
        self._space.lookup(thread_id)


@pytest.fixture
def space(tmp_path: Path) -> Workspace:
    return Workspace(tmp_path)


@pytest.fixture
def broker(space: Workspace, tmp_path: Path) -> Broker:
    return Broker(
        workspace=space,
        pool=FakePool(),  # type: ignore[arg-type]
        skills=SkillStore(tmp_path / "skills"),
        memory=MemoryStore(space),
    )


@pytest.fixture
async def client(broker: Broker) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(broker)

    async def current_broker() -> Broker:
        return broker

    # 当前受限沙箱不能使用 AnyIO 的同步依赖线程；这里只替换等价取值方式。
    app.dependency_overrides[get_broker] = current_broker
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://broker") as opened:
        yield opened


def payload(*, name: str = "project-tabs") -> dict[str, str]:
    return {
        "name": name,
        "description": "教师偏好制表符缩进",
        "type": "user",
        "content": "后续分析使用制表符缩进。",
    }


async def test_memory_http_primitives_round_trip_and_catalog_omits_content(
    client: httpx.AsyncClient, space: Workspace
) -> None:
    space.create(THREAD_ID)

    written = await client.put(f"/threads/{THREAD_ID}/memory/project-tabs", json=payload())
    catalog = await client.get(f"/threads/{THREAD_ID}/memory")
    detail = await client.get(f"/threads/{THREAD_ID}/memory/project-tabs")

    assert written.status_code == httpx.codes.OK
    assert catalog.status_code == httpx.codes.OK
    assert set(catalog.json()) == {"items"}
    assert catalog.json()["items"] == [
        {
            "slug": "project-tabs",
            "name": "project-tabs",
            "description": "教师偏好制表符缩进",
            "type": "user",
            "updated_at": written.json()["updated_at"],
        }
    ]
    assert detail.json() == written.json()
    assert detail.json()["content"] == "后续分析使用制表符缩进。"


async def test_batch_read_returns_only_requested_records_in_request_order(
    client: httpx.AsyncClient, space: Workspace
) -> None:
    space.create(THREAD_ID)
    await client.put(f"/threads/{THREAD_ID}/memory/first", json=payload(name="first"))
    await client.put(f"/threads/{THREAD_ID}/memory/second", json=payload(name="second"))

    response = await client.post(
        f"/threads/{THREAD_ID}/memory/read",
        json={"slugs": ["second", "first"]},
    )

    assert response.status_code == httpx.codes.OK
    assert [item["slug"] for item in response.json()["items"]] == ["second", "first"]
    assert all("content" in item for item in response.json()["items"])


async def test_batch_read_accepts_at_most_five_slugs(client: httpx.AsyncClient, space: Workspace) -> None:
    space.create(THREAD_ID)

    response = await client.post(
        f"/threads/{THREAD_ID}/memory/read",
        json={"slugs": [f"item-{index}" for index in range(6)]},
    )

    assert response.status_code in {httpx.codes.BAD_REQUEST, httpx.codes.UNPROCESSABLE_ENTITY}


async def test_export_and_replace_are_full_content_cas_primitives(client: httpx.AsyncClient, space: Workspace) -> None:
    space.create(THREAD_ID)
    await client.put(f"/threads/{THREAD_ID}/memory/old", json=payload(name="old"))
    exported = await client.post(f"/threads/{THREAD_ID}/memory/export")

    replaced = await client.put(
        f"/threads/{THREAD_ID}/memory",
        json={
            "expected_version": exported.json()["version"],
            "items": [
                {
                    "slug": "new",
                    **payload(name="new"),
                }
            ],
        },
    )
    after = await client.post(f"/threads/{THREAD_ID}/memory/export")

    assert exported.status_code == httpx.codes.OK
    assert exported.json()["items"][0]["content"] == "后续分析使用制表符缩进。"
    assert replaced.status_code == httpx.codes.OK
    assert replaced.json()["version"] != exported.json()["version"]
    assert [item["slug"] for item in after.json()["items"]] == ["new"]


async def test_replace_version_conflict_is_409_and_does_not_change_memory(
    client: httpx.AsyncClient, space: Workspace
) -> None:
    space.create(THREAD_ID)
    await client.put(f"/threads/{THREAD_ID}/memory/original", json=payload(name="original"))
    before = await client.post(f"/threads/{THREAD_ID}/memory/export")

    response = await client.put(
        f"/threads/{THREAD_ID}/memory",
        json={
            "expected_version": "stale",
            "items": [{"slug": "replacement", **payload(name="replacement")}],
        },
    )
    after = await client.post(f"/threads/{THREAD_ID}/memory/export")

    assert response.status_code == httpx.codes.CONFLICT
    assert after.json() == before.json()


async def test_memory_delete_removes_detail_and_catalog_entry(client: httpx.AsyncClient, space: Workspace) -> None:
    space.create(THREAD_ID)
    await client.put(f"/threads/{THREAD_ID}/memory/project-tabs", json=payload())

    deleted = await client.delete(f"/threads/{THREAD_ID}/memory/project-tabs")
    detail = await client.get(f"/threads/{THREAD_ID}/memory/project-tabs")
    catalog = await client.get(f"/threads/{THREAD_ID}/memory")

    assert deleted.status_code == httpx.codes.NO_CONTENT
    assert detail.status_code == httpx.codes.NOT_FOUND
    assert catalog.json() == {"items": []}


@pytest.mark.parametrize(
    "method,path,json",
    [
        ("GET", "/threads/deleted/memory", None),
        ("GET", "/threads/deleted/memory/item", None),
        ("POST", "/threads/deleted/memory/read", {"slugs": ["item"]}),
        ("POST", "/threads/deleted/memory/export", None),
        ("PUT", "/threads/deleted/memory", {"items": [], "expected_version": None}),
        ("PUT", "/threads/deleted/memory/item", payload()),
        ("DELETE", "/threads/deleted/memory/item", None),
    ],
)
async def test_memory_access_to_an_absent_workspace_is_404_and_never_recreates_it(
    client: httpx.AsyncClient,
    space: Workspace,
    method: str,
    path: str,
    json: object,
) -> None:
    response = await client.request(method, path, json=json)

    assert response.status_code == httpx.codes.NOT_FOUND
    assert not space.location("deleted").exists()


async def test_missing_slug_is_404_and_invalid_slug_is_400(client: httpx.AsyncClient, space: Workspace) -> None:
    space.create(THREAD_ID)

    missing = await client.get(f"/threads/{THREAD_ID}/memory/not-there")
    invalid = await client.get(f"/threads/{THREAD_ID}/memory/.hidden")

    assert missing.status_code == httpx.codes.NOT_FOUND
    assert invalid.status_code == httpx.codes.BAD_REQUEST


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "/threads/deleted/workspace/tree", None),
        ("GET", "/threads/deleted/workspace/stat?path=data.csv", None),
        ("POST", "/threads/deleted/tool/read", {"file_path": "/workspace/data.csv"}),
        ("POST", "/threads/deleted/save", {"filename": "data.csv", "content": "eA=="}),
        ("POST", "/threads/deleted/skill/align", {"skills": []}),
    ],
)
async def test_existing_broker_reads_return_404_without_resurrecting_workspace(
    client: httpx.AsyncClient,
    space: Workspace,
    method: str,
    path: str,
    body: object,
) -> None:
    response = await client.request(method, path, json=body)

    assert response.status_code == httpx.codes.NOT_FOUND
    assert not space.location("deleted").exists()


@pytest.fixture
def remote(client: httpx.AsyncClient) -> RemoteMemory:
    return RemoteMemory(BrokerConnection(client=client))


async def test_remote_memory_implements_the_recall_protocol_and_maps_content_to_body(
    remote: RemoteMemory, space: Workspace
) -> None:
    space.create(THREAD_ID)
    service: MemoryServiceProtocol = remote
    stored = StoredMemoryRecord(
        slug="project-tabs",
        name="project-tabs",
        description="教师偏好制表符缩进",
        type=MemoryType.USER.value,
        content="后续分析使用制表符缩进。",
    )

    written = await remote.write(THREAD_ID, stored)
    catalog = await service.catalog(THREAD_ID)
    selected = await service.read(THREAD_ID, (stored.slug,))
    detail = await remote.detail(THREAD_ID, stored.slug)

    assert written.body == stored.content
    assert [item.slug for item in catalog] == [stored.slug]
    assert selected == [detail]
    assert detail.body == stored.content


async def test_remote_memory_delete_and_typed_errors(remote: RemoteMemory, space: Workspace) -> None:
    space.create(THREAD_ID)
    stored = StoredMemoryRecord(
        slug="project-tabs",
        name="project-tabs",
        description="教师偏好制表符缩进",
        type="user",
        content="后续分析使用制表符缩进。",
    )
    await remote.write(THREAD_ID, stored)
    await remote.delete(THREAD_ID, stored.slug)

    with pytest.raises(FileMissingError):
        await remote.detail(THREAD_ID, stored.slug)
    with pytest.raises(ValueError):
        await remote.detail(THREAD_ID, ".hidden")
    with pytest.raises(ValueError, match="最多"):
        await remote.read(THREAD_ID, tuple(f"item-{index}" for index in range(6)))


async def test_remote_memory_list_and_replace_cover_the_worker_storage_protocol(
    remote: RemoteMemory, space: Workspace
) -> None:
    space.create(THREAD_ID)
    old = StoredMemoryRecord(
        slug="old",
        name="old",
        description="旧记忆",
        type="project",
        content="旧正文",
    )
    new = StoredMemoryRecord(
        slug="new",
        name="new",
        description="新记忆",
        type="project",
        content="新正文",
    )
    await remote.write(THREAD_ID, old)

    assert tuple(await remote.list(THREAD_ID)) == (old,)
    await remote.replace(THREAD_ID, (new,))

    assert tuple(await remote.list(THREAD_ID)) == (new,)


async def test_remote_memory_maps_capacity_and_version_conflict_errors(
    space: Workspace,
    tmp_path: Path,
) -> None:
    space.create(THREAD_ID)
    broker = Broker(
        workspace=space,
        pool=FakePool(),  # type: ignore[arg-type]
        skills=SkillStore(tmp_path / "skills"),
        memory=MemoryStore(space, max_byte=300),
    )
    app = create_app(broker)

    async def current_broker() -> Broker:
        return broker

    app.dependency_overrides[get_broker] = current_broker
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://broker") as opened:
        remote = RemoteMemory(BrokerConnection(client=opened))
        with pytest.raises(MemoryCapacityError):
            await remote.write(
                THREAD_ID,
                StoredMemoryRecord(
                    slug="large",
                    name="large",
                    description="大正文",
                    type="reference",
                    content="x" * 250,
                ),
            )
        assert not (space.lookup(THREAD_ID) / MEMORY_DIR).exists()
        with pytest.raises(MemoryVersionConflictError):
            await remote.replace(THREAD_ID, (), expected_version="stale")


async def test_destroy_closes_the_discard_acquire_race_without_recreating_workspace(
    space: Workspace,
    tmp_path: Path,
) -> None:
    space.create(THREAD_ID)
    pool = BlockingDestroyPool(space)
    broker = Broker(
        workspace=space,
        pool=pool,  # type: ignore[arg-type]
        skills=SkillStore(tmp_path / "skills"),
        memory=MemoryStore(space),
    )
    destroying = asyncio.create_task(destroy_thread(THREAD_ID, broker))
    await pool.discard_started.wait()

    stream = cast(AsyncGenerator[str], _acquire_stream(THREAD_ID, broker, "run-1"))
    acquiring = asyncio.ensure_future(anext(stream))
    await asyncio.sleep(0)

    assert not pool.acquire_started.is_set()
    pool.finish_discard.set()
    await destroying
    final = await acquiring
    await stream.aclose()

    assert pool.acquire_started.is_set()
    assert "event: error" in final
    assert not space.exists(THREAD_ID)
