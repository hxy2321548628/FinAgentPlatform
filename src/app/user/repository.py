"""`users` 表的读写。

**口令哈希不跟着 `User` 走**：它只在登录那一条路径上用得着，而 `User` 会被塞进
session、日志与响应体。把它放进公共的那个形状里，迟早会有一处顺手序列化出去。
因此单独给登录路径一个 `Credential`。
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from types import EllipsisType
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.user.model import UserRecord, UserRole

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class User:
    """一个用户。配额两项留空表示「跟着角色的默认档走」，不是「没有配额」。"""

    id: str
    name: str
    email: str
    dept: str
    role: UserRole
    is_active: bool
    quota_tokens_daily: int | None
    quota_concurrent_runs: int | None


@dataclass(frozen=True)
class Credential:
    """一个用户连同它的口令哈希，只在登录路径上用。"""

    user: User
    password_hash: str


class UserRepository:
    """`users` 表的读写。

    Args:
        engine: 到 Postgres 的异步引擎。
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def create(
        self,
        *,
        name: str,
        email: str,
        password_hash: str,
        role: UserRole,
        dept: str = "",
        is_active: bool = True,
    ) -> User:
        """建一个账号。

        Args:
            name: 用户名，全库唯一。
            email: 邮箱，全库唯一 —— **它是第二把登录钥匙**。
            password_hash: 已经算好的口令哈希，**明文不进这一层**。
            role: 角色。
            dept: 院系。只是名册上的一列，不参与任何判断。
            is_active: 建出来就能不能登。**没填邀请码的自助注册给 False** ——
                那样的账号在库里与「被管理员停用」的账号形状相同，两者都靠这一列挡在
                登录之外。分开成两种状态换不来任何决策差异：管理员对它们要做的
                都是同一个动作。

        Returns:
            建出来的用户。

        Raises:
            IntegrityError: 用户名或邮箱已被占用。
        """
        record = UserRecord(
            id=uuid4(),
            name=name,
            email=email,
            dept=dept,
            password_hash=password_hash,
            role=role,
            is_active=is_active,
            created_at=datetime.now(UTC),
        )
        # **commit 之后不能再读这一行的字段** —— 默认的 `expire_on_commit` 会让每个属性
        # 变成一次惰性重查，而那次重查是同步 IO，在异步会话里直接抛 MissingGreenlet。
        # 关掉它比 commit 前先把字段抄出来诚实：抄出来的那份迟早会漏掉后加的列
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            session.add(record)
            await session.commit()
        return _to_user(record)

    async def find_by_name(self, name: str) -> Credential | None:
        """按用户名精确查一个账号连同它的口令哈希。

        **登录不走这一条，走 `find_by_identifier`。** 这一条留给「按名字找人」的
        场景（如把某个人加进课题组）—— 那里输入的就是用户名，认成邮箱只会
        在重名与撞邮箱时给出意外的人。

        Args:
            name: 用户名。

        Returns:
            找到的凭据，否则 None。
        """
        async with AsyncSession(self._engine) as session:
            found = await session.exec(select(UserRecord).where(col(UserRecord.name) == name))
            record = found.first()
        if record is None:
            return None
        return Credential(user=_to_user(record), password_hash=record.password_hash)

    async def find_by_identifier(self, identifier: str) -> Credential | None:
        """按用户名**或**邮箱查一个账号，登录用。

        两者都全库唯一，因此这个查询至多命中一行 —— 不需要定义「先匹配哪一个」。

        Args:
            identifier: 用户名或邮箱，登录框里填的那一串。

        Returns:
            找到的凭据，否则 None。
        """
        async with AsyncSession(self._engine) as session:
            found = await session.exec(
                select(UserRecord).where((col(UserRecord.name) == identifier) | (col(UserRecord.email) == identifier))
            )
            record = found.first()
        if record is None:
            return None
        return Credential(user=_to_user(record), password_hash=record.password_hash)

    async def get(self, user_id: str) -> User | None:
        """按 id 查一个账号，不存在或 id 不是合法 uuid 时返回 None。

        Args:
            user_id: 用户标识。

        Returns:
            找到的用户，否则 None。
        """
        identifier = _parse(user_id)
        if identifier is None:
            return None
        async with AsyncSession(self._engine) as session:
            record = await session.get(UserRecord, identifier)
        return None if record is None else _to_user(record)

    async def names(self, user_ids: Sequence[str]) -> dict[str, str]:
        """一批标识对应的姓名，**一次查询取回**。

        列表里逐个查是 N 次往返，而那种慢法在开发机上量不出来。

        Args:
            user_ids: 用户标识，允许重复与非法值。

        Returns:
            标识到姓名的映射；查不到的键不出现。
        """
        wanted = {parsed for parsed in (_parse(one) for one in user_ids) if parsed is not None}
        if not wanted:
            return {}
        async with AsyncSession(self._engine) as session:
            found = await session.exec(
                select(col(UserRecord.id), col(UserRecord.name)).where(col(UserRecord.id).in_(wanted))
            )
            return {identifier.hex: name for identifier, name in found.all()}

    async def list_all(self) -> list[User]:
        """全部账号，**最近建的排在前面**。

        排序本身是答案：管理员打开这一页多半是为了处理刚注册、还在等激活的那几个人。

        Returns:
            每个账号一行。没有分页 —— 本期用户规模是一两百人。
        """
        async with AsyncSession(self._engine) as session:
            found = await session.exec(select(UserRecord).order_by(col(UserRecord.created_at).desc()))
            return [_to_user(one) for one in found.all()]

    async def set_active(self, user_id: str, *, is_active: bool) -> bool:
        """启用或停用一个账号。

        停用之后**只是登不上，数据全部留在原处** —— 学生毕业、教师离职都是常态，
        而他们的分析很可能仍属于课题组。

        Args:
            user_id: 用户标识。
            is_active: 启用还是停用。

        Returns:
            是否找到了这个账号。

        """
        identifier = _parse(user_id)
        if identifier is None:
            return False
        async with AsyncSession(self._engine) as session:
            record = await session.get(UserRecord, identifier)
            if record is None:
                return False
            record.is_active = is_active
            session.add(record)
            await session.commit()
        logger.info("账号启停：user_id=%s is_active=%s", user_id, is_active)
        return True

    async def update_profile(
        self,
        user_id: str,
        *,
        role: UserRole | EllipsisType = ...,
        quota_tokens_daily: int | EllipsisType | None = ...,
        quota_concurrent_runs: int | EllipsisType | None = ...,
        dept: str | EllipsisType = ...,
    ) -> bool:
        """改角色、配额与院系。**没传的字段原样不动。**

        **「没传」用 `...` 而不是 `None` 表示。** 配额留空是一个有意义的值 ——
        它表示「跟着角色的默认档走」。两者若都用 `None`，那么「把某个人的配额
        改回默认档」这个操作就表达不出来，调过配额的人再也回不去。

        Args:
            user_id: 用户标识。
            role: 新角色，不传则不动。
            quota_tokens_daily: 每日 token 配额；显式传 `None` 表示回到角色默认档。
            quota_concurrent_runs: 并发 run 配额；同上。
            dept: 院系，不传则不动。

        Returns:
            是否找到了这个账号。
        """
        identifier = _parse(user_id)
        if identifier is None:
            return False
        async with AsyncSession(self._engine) as session:
            record = await session.get(UserRecord, identifier)
            if record is None:
                return False
            if not isinstance(role, EllipsisType):
                record.role = role
            if not isinstance(quota_tokens_daily, EllipsisType):
                record.quota_tokens_daily = quota_tokens_daily
            if not isinstance(quota_concurrent_runs, EllipsisType):
                record.quota_concurrent_runs = quota_concurrent_runs
            if not isinstance(dept, EllipsisType):
                record.dept = dept
            session.add(record)
            await session.commit()
        logger.info("账号资料变更：user_id=%s", user_id)
        return True

    async def count(self) -> int:
        """库里一共有几个账号。

        Returns:
            行数。首个管理员的初始化只看它是不是 0。
        """
        async with AsyncSession(self._engine) as session:
            found = await session.exec(select(func.count()).select_from(UserRecord))
            return int(found.one())


def _to_user(record: UserRecord) -> User:
    return User(
        id=record.id.hex,
        name=record.name,
        email=record.email,
        dept=record.dept,
        role=record.role,
        is_active=record.is_active,
        quota_tokens_daily=record.quota_tokens_daily,
        quota_concurrent_runs=record.quota_concurrent_runs,
    )


def _parse(user_id: str) -> UUID | None:
    """用户 id 来自 session 与 URL，解析不了就是「查不到」，不是 500。"""
    try:
        return UUID(user_id)
    except ValueError:
        return None
