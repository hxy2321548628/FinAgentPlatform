"""认证端点：登录、登出、我是谁。

**这三个是仅有的不需要登录就能调的业务端点**（`/auth/me` 除外，它自己要认人）。
其余全部挂着 `require_user`，见 `api/app.py`。
"""

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Cookie, Depends, Response, status

from api.error import unauthenticated
from api.platform import Platform, get_platform
from api.schema import LoginRequest, MeResponse
from api.security import CurrentUser
from auth.session import COOKIE_NAME, Session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# 用户名不存在与口令不对给同一句话，不给试探的人区分两者的机会
LOGIN_FAILED_MESSAGE = "用户名或口令不正确"

DISABLED_MESSAGE = "账号已被禁用"

# Cookie 的三项属性。
# - HttpOnly：JS 读不到它，XSS 偷不走登录态；
# - SameSite=Lax：跨站请求不带它，挡掉 CSRF 的常见形态，而顶层跳转仍然带得上；
# - **没有 Secure**：本平台走内网 HTTP，加上它 Cookie 就一次都发不出去。
#   凭据因此在内网链路上是明文的，这一条是架构里明确接受过的风险，不是漏配。
COOKIE_HTTP_ONLY = True
COOKIE_SAME_SITE: Literal["lax"] = "lax"
COOKIE_PATH = "/"


@router.post("/login")
async def login(
    request: LoginRequest,
    response: Response,
    platform: Annotated[Platform, Depends(get_platform)],
) -> MeResponse:
    """校验用户名与口令，发一个登录态 Cookie。"""
    credential = await platform.user.find_by_name(request.name)
    if credential is None or not platform.password.verify(credential.password_hash, request.password):
        # **不记用户名之外的任何东西**，尤其不记那个试出来的口令 —— 它多半是某个人
        # 真在用的口令，只是敲错了地方
        logger.info("登录失败：name=%s", request.name)
        raise unauthenticated(LOGIN_FAILED_MESSAGE)

    if not credential.user.is_active:
        logger.info("被禁用的账号尝试登录：name=%s", request.name)
        raise unauthenticated(DISABLED_MESSAGE)

    user = credential.user
    token = await platform.session.issue(Session(user_id=user.id, name=user.name, role=user.role))
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=platform.session_ttl_second,
        httponly=COOKIE_HTTP_ONLY,
        samesite=COOKIE_SAME_SITE,
        path=COOKIE_PATH,
    )
    logger.info("登录成功：user_id=%s role=%s", user.id, user.role.value)
    return MeResponse(id=user.id, name=user.name, role=user.role)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    current: CurrentUser,
    platform: Annotated[Platform, Depends(get_platform)],
    token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> None:
    """销毁当前登录态，并让浏览器把 Cookie 也丢掉。

    **删 Redis 那一侧才是真正的登出**：只清 Cookie 的话，令牌本身还有效，
    谁抄下过它就还能继续用。
    """
    if token:
        await platform.session.revoke(token)
    response.delete_cookie(COOKIE_NAME, path=COOKIE_PATH)
    logger.info("已登出：user_id=%s", current.user_id)


@router.get("/me")
async def me(current: CurrentUser) -> MeResponse:
    """当前登录用户。未登录时是 401，不是空对象。"""
    return MeResponse(id=current.user_id, name=current.name, role=current.role)
