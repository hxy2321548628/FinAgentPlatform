"""`users` 表的读写。

**口令哈希不跟着 `User` 走**：它只在登录那一条路径上用得着，而 `User` 会被塞进
session、日志与响应体。把它放进公共的那个形状里，迟早会有一处顺手序列化出去。
因此单独给登录路径一个 `Credential`。
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from user.model import UserRecord, UserRole

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class User:
    """一个用户。配额两项留空表示「跟着角色的默认档走」，不是「没有配额」。"""

    id: str
    name: str
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

    async def create(self, *, name: str, password_hash: str, role: UserRole) -> User:
        """建一个账号。

        Args:
            name: 用户名，全库唯一。
            password_hash: 已经算好的口令哈希，**明文不进这一层**。
            role: 角色。

        Returns:
            建出来的用户。

        Raises:
            IntegrityError: 用户名已被占用。
        """
        record = UserRecord(
            id=uuid4(),
            name=name,
            password_hash=password_hash,
            role=role,
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
        """按用户名查一个账号连同它的口令哈希。

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
