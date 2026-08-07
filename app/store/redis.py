"""到 Redis 的客户端，以及启动时的一次体检。

事件通道与任务队列都落在这里。体检的理由与 Postgres 那边一样：连不上要在启动时失败。
"""

import logging

from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

# 开发机默认值，与 deploy/compose.yml 里 redis 服务对齐
DEFAULT_URL = "redis://127.0.0.1:6379/0"


class RedisUnavailableError(RuntimeError):
    """连不上 Redis。

    抛在启动路径上，让进程直接起不来。
    """


def create_client(url: str) -> Redis:
    """按 URL 建一个异步客户端。

    **解码交给客户端**：事件的信封是 JSON 文本，调用方拿到 `str` 才不必每处自己 decode。

    Args:
        url: 形如 `redis://host:6379/0`。

    Returns:
        可直接下命令的客户端。建它同样不会连接，须紧跟一次 `check`。
    """
    return Redis.from_url(url, decode_responses=True)


async def check(client: Redis) -> None:
    """确认连得上，连不上就抛。

    Args:
        client: 待体检的客户端。

    Raises:
        RedisUnavailableError: 连接不上或命令失败。
    """
    try:
        await client.ping()
    except RedisError as exc:
        message = f"连不上 Redis：{exc}"
        raise RedisUnavailableError(message) from exc
