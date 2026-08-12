"""登录态：Cookie 里只有一个不可猜的令牌，身份本身存在 Redis。

**不用 JWT**：登出要能立刻失效，而自包含的令牌做不到「立刻」—— 只能等它自己过期，
或者再维护一张吊销表，那就等于又把状态搬回了服务端。

**7 天滑动过期**：每次校验都把 TTL 推回 7 天，天天用的人不会被踢下线，
放着不管的会话一周后自己消失。

> **运维要知道的一条**：session 存 Redis 意味着 **Redis 重启会把所有人踢下线**。
> 这不是故障，是选它的代价。
"""

import secrets

from pydantic import BaseModel, Field
from redis.asyncio import Redis

from user.model import UserRole

# Cookie 名。前缀是为了在浏览器的 Cookie 列表里一眼看出它是谁的
COOKIE_NAME = "zuel_session"

KEY_PREFIX = "zuel:session:"

# 7 天，秒
DEFAULT_TTL_SECOND = 7 * 24 * 60 * 60

# 令牌的随机字节数。32 字节即 256 位，猜不动
TOKEN_BYTE = 32


class Session(BaseModel):
    """一个登录态里存的身份。

    **只存身份，不存权限判断的结果** —— 角色改了之后不必等 session 过期，
    但反过来若把「能不能做某事」缓存进来，改权限就要等一周才生效。
    """

    user_id: str = Field(min_length=1, description="用户标识")
    name: str = Field(min_length=1, description="用户名")
    role: UserRole = Field(description="角色")


class SessionStore:
    """登录态的发放、校验与销毁。

    Args:
        client: Redis 客户端。
        ttl_second: 滑动过期时长，秒。
    """

    def __init__(self, client: Redis, *, ttl_second: int = DEFAULT_TTL_SECOND) -> None:
        self._client = client
        self._ttl = ttl_second

    async def issue(self, session: Session) -> str:
        """发一个新令牌。

        Args:
            session: 要记下的身份。

        Returns:
            放进 Cookie 的令牌。
        """
        token = secrets.token_urlsafe(TOKEN_BYTE)
        await self._client.set(_key(token), session.model_dump_json(), ex=self._ttl)
        return token

    async def resolve(self, token: str) -> Session | None:
        """把令牌换回身份，并把过期时间推回去。

        取与续期是**同一条命令**（`GETEX`）：分成两步的话，两步之间令牌可能刚好过期，
        于是续了一个已经不存在的键 —— Redis 不会报错，只是什么都没发生。

        Args:
            token: Cookie 里的令牌。

        Returns:
            对应的身份；令牌不存在或已过期则 None。
        """
        found = await self._client.getex(_key(token), ex=self._ttl)
        if found is None:
            return None
        return Session.model_validate_json(found)

    async def revoke(self, token: str) -> None:
        """销毁一个令牌。登出走的就是它，之后同一个 Cookie 立刻失效。

        Args:
            token: Cookie 里的令牌。
        """
        await self._client.delete(_key(token))


def _key(token: str) -> str:
    return f"{KEY_PREFIX}{token}"
