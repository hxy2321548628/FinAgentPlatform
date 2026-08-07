"""认出当前用户的依赖项。

**挂在路由器上而不是逐个端点上**（见 `api/app.py`）：漏挂一个端点就是一个不需要登录
的入口，而这种缺口不报错 —— 只有拿浏览器去试才发现得了。

它只回答「你是谁」。「你能不能看这一条」是数据访问层的事，落在 repository 的过滤条件上。
"""

from typing import Annotated

from fastapi import Cookie, Depends, Request

from api.error import rate_limited, unauthenticated
from api.platform import Platform, get_platform
from auth.session import COOKIE_NAME, Session

# 未登录与 session 过期给同一句话：两者对使用者是同一件事 —— 重新登录
UNAUTHENTICATED_MESSAGE = "未登录或登录已过期，请重新登录"

RATE_LIMITED_MESSAGE = "操作太快了，请稍后再试"

# 认证前后按不同的东西限流：登录时还没有用户身份，只能按来源地址。
# 前缀是为了让两类键不撞 —— 否则一个 IP 后面所有人的额度会被算成一份
USER_RATE_KEY = "user"
ADDRESS_RATE_KEY = "address"

# 拿不到来源地址时的兜底键。宁可把这一小撮请求算作同一个来源，也不放行不限流
UNKNOWN_ADDRESS = "unknown"


async def require_user(
    platform: Annotated[Platform, Depends(get_platform)],
    token: Annotated[str | None, Cookie(alias=COOKIE_NAME, description="登录态令牌")] = None,
) -> Session:
    """从 Cookie 里认出当前用户，认不出就 401。

    Args:
        platform: 运行时。
        token: Cookie 里的登录令牌。

    Returns:
        当前用户的身份。

    Raises:
        ApiError: 没带 Cookie、令牌不认识，或已经过期。
    """
    if not token:
        raise unauthenticated(UNAUTHENTICATED_MESSAGE)
    session = await platform.session.resolve(token)
    if session is None:
        raise unauthenticated(UNAUTHENTICATED_MESSAGE)
    return session


# 端点要用当前用户时标这个类型。同一个请求里依赖只解析一次，
# 因此路由器上挂了一份、端点再取一次，并不会多查一遍 Redis
CurrentUser = Annotated[Session, Depends(require_user)]


async def limit_by_user(
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> None:
    """给已登录的调用方限一次频率。

    与 `require_user` 一样挂在路由器上，因此新加的端点自动被覆盖。

    Args:
        current: 当前用户。
        platform: 运行时。

    Raises:
        ApiError: 这个窗口内已经超限。
    """
    if not await platform.rate.allow(f"{USER_RATE_KEY}:{current.user_id}"):
        raise rate_limited(RATE_LIMITED_MESSAGE)


async def limit_by_address(
    request: Request,
    platform: Annotated[Platform, Depends(get_platform)],
) -> None:
    """给还没登录的调用方限一次频率。

    登录是唯一一个未认证还能打的业务端口，不限它等于把口令爆破的门开着。

    Args:
        request: 当前请求，从中取来源地址。
        platform: 运行时。

    Raises:
        ApiError: 这个窗口内已经超限。
    """
    address = request.client.host if request.client is not None else UNKNOWN_ADDRESS
    if not await platform.rate.allow(f"{ADDRESS_RATE_KEY}:{address}"):
        raise rate_limited(RATE_LIMITED_MESSAGE)
