"""产物认领与上传：broker 侧配了对象存储时的那条路。

连**真的 MinIO**，没起就 skip。用假客户端顶掉的话，验的只是「我调了 put_object」，
而这一步唯一的风险恰恰在「桶名、键、内容类型到底传对了没有」。

**走 ASGI 传输而不是真起 uvicorn**：这里验的是上传，不是传输层 ——
那一条已经由 `route_test.py` 用真端口验过了。
"""

from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from minio import Minio

from artifact.store import ArtifactStore
from broker.app import create_app
from broker.runtime import Broker
from sandbox.container import CommandResult
from sandbox.pool import QueuePositionCallback
from sandbox.remote import BrokerConnection, RemoteWorkspace
from sandbox.workspace import Workspace
from store.object import ensure_bucket
from test.conftest import SKIP_MINIO, live_minio

BROKER_URL = "http://broker.test"

PNG = b"\x89PNG\r\n\x1a\n"


class FakeContainer:
    @property
    def id(self) -> str:
        return "fake-container"

    def exec(self, command: str, *, timeout: int) -> CommandResult:
        return CommandResult(output="", exit_code=0)


class FakePool:
    async def acquire(
        self, thread_id: str, *, holder: str, on_queued: QueuePositionCallback | None = None
    ) -> FakeContainer:
        return FakeContainer()

    async def release(self, thread_id: str, *, holder: str) -> None:
        pass

    def current(self, thread_id: str) -> FakeContainer | None:
        return None


@pytest.fixture
def client() -> Minio:
    created = live_minio()
    if created is None:
        pytest.skip(SKIP_MINIO)
    return created


@pytest.fixture
def space(tmp_path: Path) -> Workspace:
    return Workspace(root=tmp_path)


@pytest.fixture
def store(client: Minio) -> Iterator[ArtifactStore]:
    """一个用完就删的桶。留着的话，跑一次门禁就多几个空桶。"""
    bucket = f"broker-test-{uuid4().hex[:8]}"
    ensure_bucket(client, bucket)
    try:
        yield ArtifactStore(client=client, bucket=bucket)
    finally:
        for one in client.list_objects(bucket, recursive=True):
            if one.object_name is not None:
                client.remove_object(bucket, one.object_name)
        client.remove_bucket(bucket)


@pytest.fixture
async def workspace(space: Workspace, store: ArtifactStore) -> AsyncIterator[RemoteWorkspace]:
    app = create_app(Broker(workspace=space, pool=FakePool(), artifact=store))  # type: ignore[arg-type]
    connection = BrokerConnection(
        base_url=BROKER_URL,
        client=httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BROKER_URL),
    )
    try:
        yield RemoteWorkspace(connection)
    finally:
        await connection.aclose()


async def test_a_collected_artifact_reports_its_object_key(
    workspace: RemoteWorkspace, space: Workspace, store: ArtifactStore, client: Minio
) -> None:
    thread_id = await workspace.create(uuid4().hex)
    since = await workspace.mark(thread_id)
    (space.path(thread_id) / "outputs" / "chart.png").write_bytes(PNG)

    collected = await workspace.collect(thread_id, since_ns=since, user_id="u-1")

    assert len(collected) == 1
    assert collected[0].path == f"{thread_id}/chart.png"
    assert collected[0].s3_key == f"tenant/u-1/thread/{thread_id}/chart.png"
    assert collected[0].mime == "image/png"
    assert collected[0].size == len(PNG)


async def test_the_bytes_really_land_in_the_bucket(
    workspace: RemoteWorkspace, space: Workspace, store: ArtifactStore, client: Minio
) -> None:
    """「报了一个 key」与「那个 key 真取得到字节」是两件事。"""
    thread_id = await workspace.create(uuid4().hex)
    since = await workspace.mark(thread_id)
    (space.path(thread_id) / "outputs" / "chart.png").write_bytes(PNG)

    collected = await workspace.collect(thread_id, since_ns=since, user_id="u-1")

    assert collected[0].s3_key is not None
    assert client.get_object(store.bucket, collected[0].s3_key).read() == PNG


async def test_two_users_land_under_different_prefixes(
    workspace: RemoteWorkspace, space: Workspace, store: ArtifactStore
) -> None:
    """租户前缀是新的越权面：两个人的产物不能落进同一个前缀。"""
    thread_id = await workspace.create(uuid4().hex)
    since = await workspace.mark(thread_id)
    (space.path(thread_id) / "outputs" / "chart.png").write_bytes(PNG)

    mine = await workspace.collect(thread_id, since_ns=since, user_id="u-1")
    yours = await workspace.collect(thread_id, since_ns=since, user_id="u-2")

    assert mine[0].s3_key is not None
    assert yours[0].s3_key is not None
    assert mine[0].s3_key.startswith("tenant/u-1/")
    assert yours[0].s3_key.startswith("tenant/u-2/")


async def test_a_nested_artifact_keeps_its_directory(
    workspace: RemoteWorkspace, space: Workspace, store: ArtifactStore
) -> None:
    """Agent 会往 outputs/ 下面再建目录，那一层结构要一路带到对象存储里。"""
    thread_id = await workspace.create(uuid4().hex)
    since = await workspace.mark(thread_id)
    nested = space.path(thread_id) / "outputs" / "figure"
    nested.mkdir(parents=True, exist_ok=True)
    (nested / "chart.png").write_bytes(PNG)

    collected = await workspace.collect(thread_id, since_ns=since, user_id="u-1")

    assert collected[0].s3_key == f"tenant/u-1/thread/{thread_id}/figure/chart.png"
