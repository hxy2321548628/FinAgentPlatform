"""取消标志：教师点了「停止」这件事，怎么从 api 进程传到 worker 进程。

**放 Redis 而不是数据库**：它短命、可过期、每个 step 边界读一次，正是 Redis 的形状；
而且 worker 侧本来就有一条到 Redis 的连接。

**只是一个标志，不是命令通道。** api 不去打断 worker —— 它没法打断，worker 在另一个
进程里。api 只是把「有人要停」记下来，worker 在自己的 step 边界上读到它就收手。
这也是为什么取消是**尽快**而不是**立刻**：正在进行的那一次模型调用会跑完，
它的 token 已经花掉了，掐掉连接也退不回来。
"""

import logging

from redis.asyncio import Redis

logger = logging.getLogger(__name__)

KEY_PREFIX = "zuel:cancel:"

# 标志留多久。要长于一个 run 可能的最长寿命（审批可以挂 24 小时），
# 否则标志先过期、worker 再回来看，就当作没人取消过
DEFAULT_TTL_SECOND = 48 * 60 * 60

FLAG_VALUE = "1"


class CancelFlag:
    """按 run 记的取消标志。

    Args:
        client: Redis 客户端。
        ttl_second: 标志留多久。
    """

    def __init__(self, client: Redis, *, ttl_second: int = DEFAULT_TTL_SECOND) -> None:
        self._client = client
        self._ttl = ttl_second

    async def raise_flag(self, run_id: str) -> None:
        """记下「这个 run 有人要停」。

        Args:
            run_id: 目标 run。
        """
        await self._client.set(_key(run_id), FLAG_VALUE, ex=self._ttl)

    async def is_raised(self, run_id: str) -> bool:
        """有没有人要停这个 run。

        Args:
            run_id: 目标 run。

        Returns:
            立过标志则 True。
        """
        return await self._client.exists(_key(run_id)) > 0

    async def clear(self, run_id: str) -> None:
        """撤掉标志。

        Args:
            run_id: 目标 run。
        """
        await self._client.delete(_key(run_id))


def _key(run_id: str) -> str:
    return f"{KEY_PREFIX}{run_id}"
