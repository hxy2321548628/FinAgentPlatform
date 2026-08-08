"""产物对象存储的测试：键的形状、类型猜测，以及真的传上去再取回来。

上传那几条连**真的 MinIO**，没起就 skip —— 与 Postgres / Redis 同一条规矩。
用假客户端顶掉的话，验的就只是「我调了 put_object」，而这一步唯一的风险恰恰在
「桶名、键、内容类型到底传对了没有」。
"""

from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from minio import Minio

from artifact.store import ArtifactStore, artifact_key, guess_mime
from store.object import ensure_bucket
from test.conftest import SKIP_MINIO, live_minio

PNG = b"\x89PNG\r\n\x1a\n"


@pytest.fixture
def client() -> Minio:
    created = live_minio()
    if created is None:
        pytest.skip(SKIP_MINIO)
    return created


@pytest.fixture
def store(client: Minio) -> Iterator[ArtifactStore]:
    """一个用完就删的桶。留着的话，跑一次门禁就多几个空桶。"""
    bucket = f"artifact-test-{uuid4().hex[:8]}"
    ensure_bucket(client, bucket)
    try:
        yield ArtifactStore(client=client, bucket=bucket)
    finally:
        for one in client.list_objects(bucket, recursive=True):
            if one.object_name is not None:
                client.remove_object(bucket, one.object_name)
        client.remove_bucket(bucket)


# ------------------------------------------------------------------------ 键
def test_the_key_puts_the_tenant_outermost() -> None:
    """「某个人的全部产物」要能靠一次前缀操作拿到，user 就得在最外层。"""
    assert artifact_key(user_id="u-1", thread_id="t-1", relative_path="chart.png") == "tenant/u-1/thread/t-1/chart.png"


def test_the_key_keeps_the_directory_under_outputs() -> None:
    """Agent 会往 outputs/ 下面再建目录，那一层结构要留着。"""
    key = artifact_key(user_id="u-1", thread_id="t-1", relative_path="figure/chart.png")

    assert key == "tenant/u-1/thread/t-1/figure/chart.png"


def test_two_users_never_share_a_thread_prefix() -> None:
    """租户隔离在这一层就是「前缀不重叠」。"""
    mine = artifact_key(user_id="u-1", thread_id="t-1", relative_path="chart.png")
    yours = artifact_key(user_id="u-2", thread_id="t-1", relative_path="chart.png")

    assert mine.rsplit("/", 1)[0] != yours.rsplit("/", 1)[0]


# --------------------------------------------------------------------- 类型
def test_a_png_is_recognised() -> None:
    assert guess_mime("chart.png") == "image/png"


def test_an_unknown_extension_falls_back_to_a_binary_stream() -> None:
    """猜不出就按二进制流回，不能因此让上传失败。"""
    assert guess_mime("model.pkl") == "application/octet-stream"


# --------------------------------------------------------------------- 上传
def test_an_uploaded_artifact_can_be_read_back(store: ArtifactStore, tmp_path: Path, client: Minio) -> None:
    chart = tmp_path / "chart.png"
    chart.write_bytes(PNG)

    stored = store.put(chart, user_id="u-1", thread_id="t-1", relative_path="chart.png")

    assert stored.s3_key == "tenant/u-1/thread/t-1/chart.png"
    assert stored.mime == "image/png"
    assert stored.size == len(PNG)
    assert client.get_object(store.bucket, stored.s3_key).read() == PNG


def test_uploading_the_same_path_twice_overwrites(store: ArtifactStore, tmp_path: Path, client: Minio) -> None:
    """同一个会话再跑一次、又画了一张同名的图，新的该盖掉旧的。"""
    chart = tmp_path / "chart.png"
    chart.write_bytes(PNG)
    store.put(chart, user_id="u-1", thread_id="t-1", relative_path="chart.png")
    chart.write_bytes(PNG + b"new")

    stored = store.put(chart, user_id="u-1", thread_id="t-1", relative_path="chart.png")

    assert stored.s3_key is not None
    assert client.get_object(store.bucket, stored.s3_key).read() == PNG + b"new"
