"""认证端点：注册、登录、登出、我是谁。

`/auth/register` 与 `/auth/login` 是整个平台仅有的两个未登录也能打的端口，
其余端点全部挂着 `require_user`（见 `api/app.py`）。

**只有这两个挂限流，而且按来源地址挂。** 另外两个要求先有一个有效 session，
而那个 session 正是从被限过流的登录里发出来的；它们各自只有一次 Redis 操作，
再限一道换不来什么。这两个不限则是另一回事 —— 那等于把口令爆破与邀请码爆破的门开着。
"""

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Cookie, Depends, Response, status
from sqlalchemy.exc import IntegrityError

from app.api.error import invalid, unauthenticated
from app.api.platform import Platform, get_platform
from app.api.schema import LoginRequest, MeResponse, RegisterRequest, RegisterResponse
from app.api.security import CurrentUser, limit_by_address
from app.auth.session import COOKIE_NAME, Session
from app.group.repository import Group
from app.user.model import UserRole

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# 用户名不存在与口令不对给同一句话，不给试探的人区分两者的机会
LOGIN_FAILED_MESSAGE = "用户名或口令不正确"

# 停用与「注册了还没被激活」在库里是同一个状态（`users.is_active`），因此提示语要
# 同时说得通 —— 分成两种状态换不来任何决策差异：管理员对这两种人做的是同一个动作
DISABLED_MESSAGE = "账号尚未启用，请联系管理员"

# 码不对与码根本不存在给同一句话。分开说等于给试探的人一个「这个组存在」的信号
INVALID_INVITE_CODE_MESSAGE = "邀请码不正确"

NAME_TAKEN_MESSAGE = "这个用户名或邮箱已经被占用了"

# Cookie 的三项属性。
# - HttpOnly：JS 读不到它，XSS 偷不走登录态；
# - SameSite=Lax：跨站请求不带它，挡掉 CSRF 的常见形态，而顶层跳转仍然带得上；
# - **没有 Secure**：本平台走内网 HTTP，加上它 Cookie 就一次都发不出去。
#   凭据因此在内网链路上是明文的，这一条是架构里明确接受过的风险，不是漏配。
COOKIE_HTTP_ONLY = True
COOKIE_SAME_SITE: Literal["lax"] = "lax"
COOKIE_PATH = "/"


@router.post("/register", dependencies=[Depends(limit_by_address)])
async def register(
    request: RegisterRequest,
    platform: Annotated[Platform, Depends(get_platform)],
) -> RegisterResponse:
    """自助建一个学生账号，填了邀请码就顺带进组。

    **先验邀请码再建号**：反过来的话，码打错一个字就留下一个自己登不上、
    管理员也不认识的账号。

    **不发 Cookie**：注册完自己去登录。少一条「未登录也能拿到登录态」的路径，
    就少一片要防的面。

    建号与入组不在同一个事务里 —— 中间失败的话人已经建出来了，只是没进组，
    他可以自己再申请一次。为这个窗口把两个仓储绑成一个事务，换来的正确性
    抵不上那份耦合。
    """
    group = await _resolve_invite(platform, request.invite_code, name=request.name)
    try:
        user = await platform.user.create(
            name=request.name,
            email=request.email,
            dept=request.dept,
            password_hash=platform.password.hash(request.password),
            role=UserRole.STUDENT,
            is_active=group is not None,
        )
    # **用户名与邮箱撞车给同一句话**：分开说等于告诉试探的人「这个邮箱注册过」，
    # 而那正是撞库要的第一条信息
    except IntegrityError as error:
        logger.info("注册撞了已有的用户名或邮箱：name=%s", request.name)
        raise invalid(NAME_TAKEN_MESSAGE) from error

    if group is not None:
        await platform.group.add_member(group_id=group.id, user_id=user.id)

    logger.info("注册成功：user_id=%s group_id=%s", user.id, group.id if group is not None else None)
    return RegisterResponse(
        id=user.id,
        name=user.name,
        role=user.role,
        is_active=user.is_active,
        group_name=group.name if group is not None else None,
    )


async def _resolve_invite(platform: Platform, code: str | None, *, name: str) -> Group | None:
    """把邀请码换成组。没填码是合法的，填错了不是。"""
    if not code:
        return None
    group = await platform.group.find_by_invite_code(code)
    if group is None:
        logger.info("注册用了不存在的邀请码：name=%s", name)
        raise invalid(INVALID_INVITE_CODE_MESSAGE)
    return group


@router.post("/login", dependencies=[Depends(limit_by_address)])
async def login(
    request: LoginRequest,
    response: Response,
    platform: Annotated[Platform, Depends(get_platform)],
) -> MeResponse:
    """校验用户名与口令，发一个登录态 Cookie。"""
    credential = await platform.user.find_by_identifier(request.name)
    if credential is None or not platform.password.verify(credential.password_hash, request.password):
        # **不记用户名之外的任何东西**，尤其不记那个试出来的口令 —— 它多半是某个人
        # 真在用的口令，只是敲错了地方
        logger.info("登录失败：name=%s", request.name)
        raise unauthenticated(LOGIN_FAILED_MESSAGE)

    if not credential.user.is_active:
        logger.info("被禁用的账号尝试登录：name=%s", request.name)
        raise unauthenticated(DISABLED_MESSAGE)

    user = credential.user
    token = await platform.session.issue(Session(user_id=user.id, name=user.name, role=user.role, email=user.email))
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=platform.session_ttl_second,
        httponly=COOKIE_HTTP_ONLY,
        samesite=COOKIE_SAME_SITE,
        path=COOKIE_PATH,
    )
    logger.info("登录成功：user_id=%s role=%s", user.id, user.role.value)
    return MeResponse(id=user.id, name=user.name, email=user.email, role=user.role)


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
    return MeResponse(id=current.user_id, name=current.name, email=current.email, role=current.role)
