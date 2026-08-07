"""认出当前用户的依赖项。

**挂在路由器上而不是逐个端点上**（见 `api/app.py`）：漏挂一个端点就是一个不需要登录
的入口，而这种缺口不报错 —— 只有拿浏览器去试才发现得了。

它只回答「你是谁」。「你能不能看这一条」是数据访问层的事，落在 repository 的过滤条件上。
"""

from typing import Annotated

from fastapi import Cookie, Depends

from api.error import unauthenticated
from api.platform import Platform, get_platform
from auth.session import COOKIE_NAME, Session

# 未登录与 session 过期给同一句话：两者对使用者是同一件事 —— 重新登录
UNAUTHENTICATED_MESSAGE = "未登录或登录已过期，请重新登录"


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
