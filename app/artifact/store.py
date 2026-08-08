"""把产物放进对象存储，路径按租户前缀隔离。

**只有 broker 用这个类。** 产物的字节躺在宿主机的 workspace 里，broker 是唯一碰得到
那些文件的进程 —— 让 api 或 worker 来传，就得先把字节经 HTTP 搬过去，凭空多一跳，
还得给它们开一条本来不需要的文件通路。
"""

import mimetypes
from datetime import timedelta
from pathlib import Path

from minio import Minio

from artifact.model import CollectedArtifact

# 键的前缀。**user 在最外层**：桶策略与将来的生命周期规则都按前缀写，
# 「某个人的全部产物」才是一次前缀操作而不是一次全桶扫描
TENANT_SEGMENT = "tenant"
THREAD_SEGMENT = "thread"

# 猜不出扩展名时的类型。产物多半是图，但也可能是 Excel、pickle 或别的什么
DEFAULT_MIME = "application/octet-stream"

# 预签名 URL 的有效期。它只在 nginx 与 MinIO 之间走一趟，几秒就够 ——
# 给一分钟是留给慢盘与重试，再长就只是白白延长一条能下载的凭证的寿命
PRESIGN_TTL = timedelta(minutes=1)


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

    def presign(self, s3_key: str) -> str:
        """签一条限时的下载 URL，**只发给 nginx，不发给浏览器**。

        签名里带着 MinIO 的地址，那个地址浏览器够不着（服务不对外暴露端口）。
        它经 `X-Accel-Redirect` 交给 nginx，由 nginx 取字节转给浏览器 ——
        api 进程因此一个字节都不经手，而 MinIO 也不必开一个对外的面。

        Args:
            s3_key: 对象存储里的键。

        Returns:
            带签名的完整 URL。

        Raises:
            S3Error: 签不出来。
        """
        return self._client.presigned_get_object(self.bucket, s3_key, expires=PRESIGN_TTL)

    def get(self, s3_key: str) -> bytes:
        """把一个产物整个读回内存。

        **只给「没有 nginx」的那条路用**（开发机直接跑 uvicorn）。生产走
        `presign` + `X-Accel-Redirect`，字节根本不进这个进程。

        Args:
            s3_key: 对象存储里的键。

        Returns:
            产物内容。

        Raises:
            S3Error: 对象不存在，或连不上。
        """
        response = self._client.get_object(self.bucket, s3_key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()
