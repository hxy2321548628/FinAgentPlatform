"""到 MinIO 的客户端，以及启动时的一次建桶。

**只有 broker 建这个客户端。** 产物的字节躺在宿主机的 workspace 里，而 broker 是唯一
碰得到那些文件的进程 —— 让 api 或 worker 来传，就得先把字节经 HTTP 搬过去，
凭空多一跳，还得给它们开一条本来不需要的文件通路。

桶在启动时建一次而不是每次上传前查一次：`bucket_exists` 是一次网络往返，
而桶只可能在第一次启动时不存在。
"""

import logging

import urllib3
from minio import Minio
from minio.error import S3Error

logger = logging.getLogger(__name__)

# 连不上时 minio 抛的不是 S3Error 而是底层 urllib3 的异常，OSError 也接不住它。
# 三类一起兜，否则「MinIO 没起」会以一个不指向配置的堆栈冒出来
CONNECT_ERROR = (S3Error, urllib3.exceptions.HTTPError, OSError)

# 开发机与 CI 的默认值。compose 里 minio 服务名即主机名，端口是 S3 API 的 9000
DEFAULT_ENDPOINT = "127.0.0.1:9000"
DEFAULT_ACCESS_KEY = "zuel"
DEFAULT_SECRET_KEY = "zuel-minio"
DEFAULT_BUCKET = "artifact"


class ObjectStoreUnavailableError(RuntimeError):
    """连不上 MinIO，或桶建不出来。

    抛在启动路径上，让进程直接起不来 —— 与 Postgres 那一条同一个理由：
    「能启动但一传就 500」会让之后每一次故障都多一个候选原因。
    """


def create_client(
    *,
    endpoint: str,
    access_key: str,
    secret_key: str,
    secure: bool,
    http_client: urllib3.PoolManager | None = None,
) -> Minio:
    """按配置造一个 MinIO 客户端。

    Args:
        endpoint: `host:port`，不带协议前缀。
        access_key: 访问凭据。
        secret_key: 访问密钥。
        secure: 走不走 TLS。内网无域名，默认不走（ADR-0012）。
        http_client: 自定义的连接池。留空即默认的重试与超时；探活时换成不重试的那种。

    Returns:
        可直接用的客户端。这一步不发请求，连不上要等到第一次调用才知道。
    """
    return Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure, http_client=http_client)


def ensure_bucket(client: Minio, bucket: str) -> None:
    """确保桶存在，没有就建一个。

    Args:
        client: MinIO 客户端。
        bucket: 桶名。

    Raises:
        ObjectStoreUnavailableError: 连不上，或桶建不出来。
    """
    try:
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
            logger.info("建出对象存储的桶：%s", bucket)
    except CONNECT_ERROR as exc:
        message = f"对象存储不可用：{exc}"
        raise ObjectStoreUnavailableError(message) from exc
