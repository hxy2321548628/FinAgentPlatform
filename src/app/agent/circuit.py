"""MCP 的熔断：连续失败到阈值就自动停用，成功一次即清零。

**计数在 Redis，停用状态落 Postgres。** 计数必须在 Redis —— 数它的是 api 与 worker
两个进程（管理员探活在前者，装配与工具调用在后者），进程内计数各算各的，阈值就被乘了
一遍；而且 worker 一重启就清零，那道闸等于没有。停用状态必须
落库 —— 它要被装配层、目录列表与管理员后台三处读到，而 Redis 重启会把它冲掉。

**只数传输层失败与超时，工具自己报错（`isError`）不计。** 反过来的代价更差：模型传
错参数在一次分析里连着发生 5 次很常见，那会把一个健康服务停掉，而恢复要管理员手动点。
**主动接受的代价**：一个「HTTP 200 但永远返回 `isError`」的服务（比如它自己的数据库
挂了）会一直挂在目录里，每个勾了它的教师都要浪费一次工具调用。

**三条路共用同一个计数器**：装配、单次工具调用、管理员探活。验收判据走的是探活那条
（免费且确定），而真实场景里失败大多来自装配 —— 不共用的话，判据验的是一条没人走的
路，**而它照样绿**。
"""

import logging
from typing import Protocol

from redis.asyncio import Redis

logger = logging.getLogger(__name__)

# 连续失败几次就自动停用。**这个数是猜的，列为观察项**
MCP_FAILURE_THRESHOLD = 5

KEY_PREFIX = "zuel:mcp:failure:"

# 计数器多久不动就自己过期。**这不是熔断窗口** —— 判据是「中间没有成功过」，
# 不是「N 秒内失败了 5 次」。设过期只为了不让早就下线的服务在 Redis 里留一个死键
FAILURE_TTL_SECOND = 7 * 24 * 3600


class McpDisablerProtocol(Protocol):
    """熔断对目录层的全部要求。"""

    async def disable_for_failure(self, server_id: str, *, reason: str) -> bool:
        """把一个还在用的服务转成停用，并记下原因。"""
        ...


class McpCircuit:
    """一个服务连续失败了几次，以及到阈值之后怎么办。

    Args:
        client: Redis 客户端，计数放这里。
        disabler: 目录层，到阈值时由它写库。
        threshold: 连续失败几次算停用。
    """

    def __init__(
        self,
        client: Redis,
        disabler: McpDisablerProtocol,
        *,
        threshold: int = MCP_FAILURE_THRESHOLD,
    ) -> None:
        self._client = client
        self._disabler = disabler
        self._threshold = threshold

    async def record_failure(self, server_id: str, *, reason: str) -> None:
        """记一次传输层失败；到阈值就停用这个服务。

        Args:
            server_id: 目录记录标识。
            reason: 这一次为什么失败，会写进停用原因给管理员看。
        """
        counting = self._client.pipeline()
        counting.incr(self._key(server_id))
        counting.expire(self._key(server_id), FAILURE_TTL_SECOND)
        current, _ = await counting.execute()
        count = int(current)
        if count < self._threshold:
            logger.warning("MCP 失败计数：server_id=%s count=%s/%s %s", server_id, count, self._threshold, reason)
            return
        # 库里那条更新只对还在 `enabled` 的行生效，因此并发的两条失败路径只写一次
        if await self._disabler.disable_for_failure(server_id, reason=f"连续失败 {count} 次，最后一次：{reason}"):
            logger.warning("MCP 达到失败阈值，已自动停用：server_id=%s count=%s %s", server_id, count, reason)

    async def record_success(self, server_id: str) -> None:
        """成功一次即清零。

        **不顺手把服务改回 `enabled`**：自动停用之后要不要恢复是管理员的判断 ——
        一个时好时坏的服务自己爬回目录，比它一直停着更难查。
        """
        await self._client.delete(self._key(server_id))

    async def reset(self, server_id: str) -> None:
        """管理员手动恢复时清零，让计数与状态对得上。"""
        await self._client.delete(self._key(server_id))

    async def failure_count(self, server_id: str) -> int:
        """当前连续失败了几次，给后台显示用。"""
        current = await self._client.get(self._key(server_id))
        return 0 if current is None else int(current)

    def _key(self, server_id: str) -> str:
        return f"{KEY_PREFIX}{server_id}"
