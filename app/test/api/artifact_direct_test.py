"""产物走对象存储那条路：新形状 id、租户隔离、以及 nginx 直发的那个头。

连**真的 MinIO**，没起就 skip。这个文件覆盖掉 `artifact_store` 夹具，把整条链路
（agent 写文件 → broker 传 MinIO → worker 落表 → 端点按主键取）真的串起来 ——
`artifact_test.py` 那一包仍跑在「没有对象存储」的降级路径上，两边合起来才是
兼容期的全部形态。
"""

import json
from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from minio import Minio

from api.platform import Platform
from api.route.artifact import ACCEL_REDIRECT_HEADER
from artifact.store import ArtifactStore
from auth.password import PasswordHasher
from store.object import ensure_bucket
from test.api.conftest import Agent, drain, login, signup
from test.conftest import SKIP_MINIO, live_minio

PNG = b"\x89PNG\r\n\x1a\n"


@pytest.fixture
def client_minio() -> Minio:
    created = live_minio()
    if created is None:
        pytest.skip(SKIP_MINIO)
    return created


@pytest.fixture
def store(client_minio: Minio) -> Iterator[ArtifactStore]:
    """一个用完就删的桶。"""
    bucket = f"api-test-{uuid4().hex[:8]}"
    ensure_bucket(client_minio, bucket)
    try:
        yield ArtifactStore(client=client_minio, bucket=bucket)
    finally:
        for one in client_minio.list_objects(bucket, recursive=True):
            if one.object_name is not None:
                client_minio.remove_object(bucket, one.object_name)
        client_minio.remove_bucket(bucket)


@pytest.fixture
def artifact_store(store: ArtifactStore) -> ArtifactStore:
    """覆盖 conftest 里那个「不配对象存储」的默认值。"""
    return store


def produce(client: TestClient, thread_id: str, agent: Agent, name: str = "chart.png") -> list[str]:
    """跑一次假分析，返回 run.finished 报出来的产物标识。"""
    agent.produce = {name: PNG}
    run_id = client.post(f"/api/threads/{thread_id}/runs", json={"content": "画个图"}).json()["id"]
    line = drain(client, run_id)
    finished = json.loads(next(one for one in line if '"run.finished"' in one).partition(": ")[2])
    reported: list[str] = finished["data"]["artifacts"]
    return reported


def test_a_stored_artifact_is_reported_by_its_table_id(client: TestClient, thread_id: str, agent: Agent) -> None:
    """进了对象存储就报表主键 —— 那一形状不含 `/`，端点据此与旧形状分辨。"""
    reported = produce(client, thread_id, agent)

    assert len(reported) == 1
    assert "/" not in reported[0]


def test_an_artifact_fetched_by_its_table_id_comes_back(client: TestClient, thread_id: str, agent: Agent) -> None:
    """事件给的标识拼上端点就该能下载，换了形状也一样。"""
    reported = produce(client, thread_id, agent)

    response = client.get(f"/api/artifacts/{reported[0]}")

    assert response.status_code == 200
    assert response.content == PNG
    assert response.headers["content-type"] == "image/png"


def test_someone_elses_artifact_is_not_found(
    client: TestClient, thread_id: str, agent: Agent, platform: Platform, hasher: PasswordHasher
) -> None:
    """表主键是新的越权面：换个人来取，要与「不存在」给同一个回答。"""
    reported = produce(client, thread_id, agent)
    stranger = signup(client, platform, hasher, name=f"stranger-{uuid4().hex[:8]}")
    client.cookies.clear()
    login(client, stranger.name)

    assert client.get(f"/api/artifacts/{reported[0]}").status_code == 404


def test_a_malformed_table_id_is_not_found(client: TestClient) -> None:
    """路径参数什么都可能来。解不成 UUID 该是 404，不是 500。"""
    assert client.get("/api/artifacts/not-a-uuid").status_code == 404


def test_the_legacy_shape_still_opens_a_stored_artifact(client: TestClient, thread_id: str, agent: Agent) -> None:
    """保留期内的历史事件指着旧形状，而那些产物现在已经在对象存储里了。"""
    produce(client, thread_id, agent)

    response = client.get(f"/api/artifacts/{thread_id}/chart.png")

    assert response.status_code == 200
    assert response.content == PNG


class TestDirectSend:
    """开了 nginx 直发的那一组。夹具覆盖只在这个类里生效。"""

    @pytest.fixture
    def artifact_direct_send(self) -> bool:
        return True

    def test_the_bytes_are_handed_to_nginx(
        self, client: TestClient, thread_id: str, agent: Agent, store: ArtifactStore
    ) -> None:
        """响应体是空的，字节由 nginx 按这个头自己去 MinIO 取。

        **这正是「api 进程碰不到字节」的字面含义** —— 响应体里一个字节都没有。
        """
        reported = produce(client, thread_id, agent)

        response = client.get(f"/api/artifacts/{reported[0]}")

        assert response.content == b""
        assert response.headers["content-type"].startswith("image/png")

    def test_the_redirect_target_is_a_signed_object_url(
        self, client: TestClient, thread_id: str, agent: Agent, store: ArtifactStore
    ) -> None:
        """目标要落在 nginx 那条 internal location 上，且带着签名。

        前缀就是桶名 —— nginx 按它匹配，把 /{桶}/{键}?{签名} 原样转给 MinIO，
        路径一个字符都不改写。
        """
        reported = produce(client, thread_id, agent)

        target = client.get(f"/api/artifacts/{reported[0]}").headers[ACCEL_REDIRECT_HEADER]

        assert target.startswith(f"/{store.bucket}/tenant/")
        assert "X-Amz-Signature=" in target

    def test_the_legacy_shape_is_handed_over_too(
        self, client: TestClient, thread_id: str, agent: Agent, store: ArtifactStore
    ) -> None:
        """旧形状只要查得到表行就同样走直发，不该退化成由 api 转发字节。"""
        produce(client, thread_id, agent)

        response = client.get(f"/api/artifacts/{thread_id}/chart.png")

        assert response.content == b""
        assert ACCEL_REDIRECT_HEADER in response.headers
