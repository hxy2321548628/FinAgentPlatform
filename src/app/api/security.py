"""认出当前用户的依赖项。

**挂在路由器上而不是逐个端点上**（见 `api/app.py`）：漏挂一个端点就是一个不需要登录
的入口，而这种缺口不报错 —— 只有拿浏览器去试才发现得了。

它只回答「你是谁」。「你能不能看这一条」是数据访问层的事，落在 repository 的过滤条件上。
"""

from typing import Annotated

from fastapi import Cookie, Depends, Request

from app.api.error import forbidden, rate_limited, unauthenticated
from app.api.platform import Platform, get_platform
from app.auth.session import COOKIE_NAME, Session
from app.user.model import UserRole

# 未登录与 session 过期给同一句话：两者对使用者是同一件事 —— 重新登录
UNAUTHENTICATED_MESSAGE = "未登录或登录已过期，请重新登录"

RATE_LIMITED_MESSAGE = "操作太快了，请稍后再试"

NOT_ADMIN_MESSAGE = "需要管理员权限"

NOT_REVIEWER_MESSAGE = "需要审核员权限"

# 审核端点认这两个角色。**`admin` 在里面，`reviewer` 不在管理端点里** ——
# 这两句不对称是有意的：多给管理员一样能力不改变任何边界（他本来就能改任何账号的角色，
# 想审的话给自己加一个角色就行），而多给 reviewer 一样能力就让这个角色退化成 admin 的别名
REVIEWER_ROLE = frozenset({UserRole.ADMIN, UserRole.REVIEWER})

# 认证前后按不同的东西限流：登录时还没有用户身份，只能按来源地址。
# 前缀是为了让两类键不撞 —— 否则一个 IP 后面所有人的额度会被算成一份
USER_RATE_KEY = "user"
ADDRESS_RATE_KEY = "address"

# 事件流单独一本账。**断线重连是长连接的常态，而每次重连都要过这道闸** ——
# 与普通请求共用计数器时，一条反复重连的流会把整个界面的额度吃光，且它自持：
# 重连快过窗口清空的速度，闸门就再也开不了。症状是「点什么都是 429」，
# 而没有一处指得出源头是一条流。**仍旧限它**，只是各算各的 ——
# 不限的话，开无限条流就没有任何东西拦得住。
STREAM_RATE_KEY = "stream"

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


async def require_admin(current: CurrentUser) -> Session:
    """认出当前用户并要求它是管理员，不是就 403。

    **这里给 403 而不是 404。** 越权访问**他人的资源**要伪装成 404，否则那个回答本身
    就确认了资源存在、可以被拿来探测；而「你不是管理员」不泄露任何东西 ——
    管理端点存不存在本来就写在 `/docs` 上。

    Args:
        current: 当前用户。

    Returns:
        当前用户的身份。

    Raises:
        ApiError: 已登录但不是管理员。
    """
    if current.role is not UserRole.ADMIN:
        raise forbidden(NOT_ADMIN_MESSAGE)
    return current


# 只有管理员打得开的端点标这个类型
AdminUser = Annotated[Session, Depends(require_admin)]


async def require_reviewer(current: CurrentUser) -> Session:
    """认出当前用户并要求它审得了，不是就 403。

    **`admin` 同时满足，反过来不成立。** `reviewer` 只有「看审核队列」与
    「通过 / 拒绝」两样，账号与配额一样都碰不到 —— 一旦让它顺手多拿一样，
    这个角色就退化成 `admin` 的别名，而设它的全部意义正是把审核这一件事单独交出去。

    **这里给 403 而不是 404**，与 `require_admin` 同一条理由：「你的角色不够」
    不泄露任何东西，管理端点存不存在本来就写在 `/docs` 上。

    Args:
        current: 当前用户。

    Returns:
        当前用户的身份。

    Raises:
        ApiError: 已登录但既不是审核员也不是管理员。
    """
    if current.role not in REVIEWER_ROLE:
        raise forbidden(NOT_REVIEWER_MESSAGE)
    return current


# 审核端点标这个类型
ReviewerUser = Annotated[Session, Depends(require_reviewer)]


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


async def limit_stream_by_user(
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
) -> None:
    """给事件流订阅限一次频率，走的是与普通请求分开的那本账。

    Args:
        current: 当前用户。
        platform: 运行时。

    Raises:
        ApiError: 这个窗口内已经超限。
    """
    if not await platform.rate.allow(f"{STREAM_RATE_KEY}:{current.user_id}"):
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
