"""把产物放进对象存储，路径按租户前缀隔离。

**只有 broker 用这个类。** 产物的字节躺在宿主机的 workspace 里，broker 是唯一碰得到
那些文件的进程 —— 让 api 或 worker 来传，就得先把字节经 HTTP 搬过去，凭空多一跳，
还得给它们开一条本来不需要的文件通路。
"""

import mimetypes
from pathlib import Path

from minio import Minio

from artifact.model import CollectedArtifact

# 键的前缀。**user 在最外层**：桶策略与将来的生命周期规则都按前缀写，
# 「某个人的全部产物」才是一次前缀操作而不是一次全桶扫描
TENANT_SEGMENT = "tenant"
THREAD_SEGMENT = "thread"

# 猜不出扩展名时的类型。产物多半是图，但也可能是 Excel、pickle 或别的什么
DEFAULT_MIME = "application/octet-stream"


def artifact_key(*, user_id: str, thread_id: str, relative_path: str) -> str:
    """产物在对象存储里的键。

    Args:
        user_id: 产出它的人，租户前缀就是它。
        thread_id: 产出它的会话。
        relative_path: 在 `outputs/` 下的相对路径，可以带目录层级。

    Returns:
        形如 `tenant/{user_id}/thread/{thread_id}/{relative_path}` 的键。
    """
    return f"{TENANT_SEGMENT}/{user_id}/{THREAD_SEGMENT}/{thread_id}/{relative_path}"


def guess_mime(relative_path: str) -> str:
    """按扩展名猜内容类型。

    Args:
        relative_path: 产物的路径或文件名。

    Returns:
        猜出来的类型，猜不出则二进制流。
    """
    guessed, _ = mimetypes.guess_type(relative_path)
    return guessed or DEFAULT_MIME


class ArtifactStore:
    """产物在对象存储里的写入口。

    Args:
        client: MinIO 客户端。
        bucket: 桶名，需已存在（建桶在启动路径上做一次）。
    """

    def __init__(self, client: Minio, bucket: str) -> None:
        self._client = client
        self.bucket = bucket

    def put(self, path: Path, *, user_id: str, thread_id: str, relative_path: str) -> CollectedArtifact:
        """把一个产物文件传上去。

        **同名即覆盖**：同一个会话再跑一次、又画了一张同名的图，新的就该盖掉旧的 ——
        教师看到的永远是最近一次的结果。

        Args:
            path: 宿主机上的产物文件。
            user_id: 产出它的人。
            thread_id: 产出它的会话。
            relative_path: 在 `outputs/` 下的相对路径。

        Returns:
            这个产物的键、类型与字节数。

        Raises:
            S3Error: 桶不存在、凭据不对，或服务端拒绝。
        """
        key = artifact_key(user_id=user_id, thread_id=thread_id, relative_path=relative_path)
        mime = guess_mime(relative_path)
        self._client.fput_object(self.bucket, key, str(path), content_type=mime)
        return CollectedArtifact(
            path=f"{thread_id}/{relative_path}",
            mime=mime,
            size=path.stat().st_size,
            s3_key=key,
        )
