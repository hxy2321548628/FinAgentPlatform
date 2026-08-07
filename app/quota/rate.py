"""接口频率限制：Redis 里的滑动窗口计数。

**滑动窗口而不是固定窗口**：固定窗口在两个窗口的接缝处允许两倍的量 ——
59 秒打满一轮、61 秒再打满一轮，两秒内就是两倍上限。

**先数再记**：被拒的那一次不该占掉一个名额，否则一旦超限，之后每次尝试都在
给自己续命，窗口永远清不空。

用 Redis 而不是进程内计数：api 可以有多个副本，进程内的计数各算各的，
上限就被副本数乘了一遍。
"""

import time
import uuid

from redis.asyncio import Redis

KEY_PREFIX = "zuel:rate:"


class RateLimiter:
    """按某个键限制单位时间内的请求数。

    键是什么由调用方决定：认证后的端点按用户，登录端点按来源地址 ——
    未登录的人没有用户身份，而登录恰恰是最该限的那一个。

    Args:
        client: Redis 客户端。
        limit: 窗口内允许的次数。
        window_second: 窗口长度，秒。
    """

    def __init__(self, client: Redis, *, limit: int, window_second: int) -> None:
        self._client = client
        self._limit = limit
        self._window = window_second

    async def allow(self, key: str) -> bool:
        """记一次请求，并回答它是否放行。

        Args:
            key: 限流键。

        Returns:
            放行则 True；这个窗口内已经超限则 False，且不记这一次。
        """
        now = time.time()
        target = f"{KEY_PREFIX}{key}"

        counting = self._client.pipeline()
        counting.zremrangebyscore(target, 0, now - self._window)
        counting.zcard(target)
        _, current = await counting.execute()

        if int(current) >= self._limit:
            return False

        recording = self._client.pipeline()
        # 成员必须唯一，否则同一毫秒内的两次请求会覆盖成一条，窗口里少算一次
        recording.zadd(target, {uuid.uuid4().hex: now})
        recording.expire(target, self._window)
        await recording.execute()
        return True
