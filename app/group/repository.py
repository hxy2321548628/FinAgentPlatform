"""组、名册与入组申请的读写。

**这一层不做权限判断，只回答「谁在哪个组」。** 「你是不是这个组的组主」由端点比对
`Group.owner_id` 得出 —— 把它做成查询条件的话，将来多一种能管组的人就要改遍每一个方法。

**邀请码不在 `GroupSummary` 里。** 浏览列表是所有登录用户都看得到的，而邀请码是准入
凭证；跟着列表发出去就等于没有准入。它只出现在 `Group` 上，端点只把组主那一份回传。

两个仓储的分界是「名册」与「申请」。唯一的例外是批准 ——
批准与入组写在同一个事务里，理由见 `JoinRequestRepository.decide`。
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Select, func, update
from sqlalchemy import select as sa_select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from group.model import GroupMemberRecord, GroupRecord, JoinRequestRecord, JoinRequestStatus, new_invite_code
from user.model import UserRecord, UserRole

logger = logging.getLogger(__name__)

# 申请连同两头名字的那七列。写全类型是为了按位置取值时仍然查得出错 ——
# 七列超过了 `session.exec` 的重载上限，因此这条查询走连接，取回来的是裸的行
DetailRow = tuple[UUID, UUID, str, UUID, str, JoinRequestStatus, datetime]


@dataclass(frozen=True)
class Group:
    """一个课题组。**带着邀请码**，因此只回传给组主。"""

    id: str
    name: str
    owner_id: str
    invite_code: str


@dataclass(frozen=True)
class GroupSummary:
    """浏览列表里的一个组。学生凭「谁带的、多少人」挑组，因此这两项都在。"""

    id: str
    name: str
    owner_name: str
    member_count: int


@dataclass(frozen=True)
class GroupMember:
    """名册上的一个人。"""

    user_id: str
    name: str
    role: UserRole


@dataclass(frozen=True)
class JoinRequest:
    """一条入组申请。"""

    id: str
    group_id: str
    user_id: str
    status: JoinRequestStatus
    created_at: datetime


@dataclass(frozen=True)
class JoinRequestDetail:
    """一条申请连同两头的名字。

    教师的待办列表与学生的「我申请了哪些组」共用这一个形状 —— 两边都需要一个名字来
    显示，只是各自关心的那一头不同。
    """

    id: str
    group_id: str
    group_name: str
    user_id: str
    user_name: str
    status: JoinRequestStatus
    created_at: datetime


class GroupRepository:
    """`groups` 与 `user_groups` 两张表的读写。

    Args:
        engine: 到 Postgres 的异步引擎。
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def create(self, *, name: str, owner_id: str) -> Group:
        """建一个组，**组主当场进名册**。

        组主不在自己的名册里的话，「我的组」就查不到它 —— 那条查询走的正是成员表。

        邀请码随机生成。撞码的概率是 32 的 8 次方分之一，真撞上时表现为这次建组失败、
        重试即可；为它写一圈重试代码不如把这句话写在这里。

        Args:
            name: 组名，全库唯一。
            owner_id: 组主，必须是已存在的账号。

        Returns:
            建出来的组，带邀请码。

        Raises:
            IntegrityError: 组名已被占用，或组主不存在。
        """
        record = GroupRecord(
            id=uuid4(),
            name=name,
            owner_id=UUID(owner_id),
            invite_code=new_invite_code(),
            created_at=datetime.now(UTC),
        )
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            session.add(record)
            # **组行要先落库再加成员行**：两张表之间只有外键、没有 relationship，
            # 而插入顺序只按 relationship 排 —— 一起 add 的话成员行可能排在前面，
            # 当场撞在外键上。两句仍在同一个事务里
            await session.flush()
            session.add(GroupMemberRecord(user_id=record.owner_id, group_id=record.id))
            await session.commit()
        logger.info("建组：group_id=%s owner_id=%s", record.id.hex, owner_id)
        return _to_group(record)

    async def get(self, group_id: str) -> Group | None:
        """按 id 查一个组，不存在或 id 不是合法 uuid 时返回 None。

        Args:
            group_id: 组标识。

        Returns:
            找到的组，否则 None。
        """
        identifier = _parse(group_id)
        if identifier is None:
            return None
        async with AsyncSession(self._engine) as session:
            record = await session.get(GroupRecord, identifier)
        return None if record is None else _to_group(record)

    async def find_by_invite_code(self, code: str) -> Group | None:
        """按邀请码查一个组。

        Args:
            code: 邀请码。

        Returns:
            找到的组，否则 None。

        """
        async with AsyncSession(self._engine) as session:
            found = await session.exec(select(GroupRecord).where(col(GroupRecord.invite_code) == code))
            record = found.first()
        return None if record is None else _to_group(record)

    async def is_member(self, *, group_id: str, user_id: str) -> bool:
        """这个人在不在这个组里。

        Args:
            group_id: 组标识。
            user_id: 用户标识。

        Returns:
            在名册上则 True。
        """
        identifier, member = _parse(group_id), _parse(user_id)
        if identifier is None or member is None:
            return False
        async with AsyncSession(self._engine) as session:
            found = await session.get(GroupMemberRecord, (member, identifier))
        return found is not None

    async def add_member(self, *, group_id: str, user_id: str) -> bool:
        """把一个人加进名册。

        **走 ON CONFLICT DO NOTHING 而不是「先查再插」**：教师连点两次时那两条请求
        可能并发，先查再插会有一条撞在主键上抛出去 —— 而重复添加本来就该是无事发生。

        Args:
            group_id: 组标识。
            user_id: 用户标识。

        Returns:
            这一次是否真的加了人。已经在组里则 False。
        """
        identifier, member = _parse(group_id), _parse(user_id)
        if identifier is None or member is None:
            return False
        # **靠 RETURNING 而不是 rowcount 判断有没有真的插进去**：这套驱动在插入上
        # 给回的 rowcount 是 -1，据此判断的话每一次添加都会被报成「已经在组里」。
        # 冲突时 ON CONFLICT DO NOTHING 不返回任何行，正好是要的答案
        statement = (
            insert(GroupMemberRecord)
            .values(user_id=member, group_id=identifier)
            .on_conflict_do_nothing()
            .returning(col(GroupMemberRecord.user_id))
        )
        async with self._engine.begin() as connection:
            inserted = (await connection.execute(statement)).first()
        return inserted is not None

    async def remove_member(self, *, group_id: str, user_id: str) -> None:
        """把一个人移出名册，不在里面时无事发生。

        Args:
            group_id: 组标识。
            user_id: 用户标识。
        """
        identifier, member = _parse(group_id), _parse(user_id)
        if identifier is None or member is None:
            return
        async with AsyncSession(self._engine) as session:
            record = await session.get(GroupMemberRecord, (member, identifier))
            if record is None:
                return
            await session.delete(record)
            await session.commit()

    async def list_member(self, group_id: str) -> list[GroupMember]:
        """一个组的名册，按用户名排。

        Args:
            group_id: 组标识。

        Returns:
            组里的每个人一行，含姓名与角色 —— 只有 uuid 的话教师认不出谁是谁。
        """
        identifier = _parse(group_id)
        if identifier is None:
            return []
        statement = (
            sa_select(col(UserRecord.id), col(UserRecord.name), col(UserRecord.role))
            .join(GroupMemberRecord, onclause=col(GroupMemberRecord.user_id) == col(UserRecord.id))
            .where(col(GroupMemberRecord.group_id) == identifier)
            .order_by(col(UserRecord.name))
        )
        async with self._engine.connect() as connection:
            found = (await connection.execute(statement)).all()
        return [GroupMember(user_id=row[0].hex, name=row[1], role=row[2]) for row in found]

    async def list_all(self) -> list[GroupSummary]:
        """全部组，按组名排。**不含邀请码**。

        Returns:
            每个组一行，带组主姓名与人数。
        """
        statement = (
            sa_select(
                col(GroupRecord.id),
                col(GroupRecord.name),
                col(UserRecord.name),
                func.count(col(GroupMemberRecord.user_id)),
            )
            .join(UserRecord, onclause=col(UserRecord.id) == col(GroupRecord.owner_id))
            .outerjoin(GroupMemberRecord, onclause=col(GroupMemberRecord.group_id) == col(GroupRecord.id))
            .group_by(col(GroupRecord.id), col(GroupRecord.name), col(UserRecord.name))
            .order_by(col(GroupRecord.name))
        )
        async with self._engine.connect() as connection:
            found = (await connection.execute(statement)).all()
        return [GroupSummary(id=row[0].hex, name=row[1], owner_name=row[2], member_count=row[3]) for row in found]

    async def list_for_user(self, user_id: str) -> list[Group]:
        """这个人所属的全部组，按组名排。

        Args:
            user_id: 用户标识。

        Returns:
            所属的组；一个都没有则空列表。
        """
        member = _parse(user_id)
        if member is None:
            return []
        async with AsyncSession(self._engine) as session:
            found = await session.exec(
                select(GroupRecord)
                .join(GroupMemberRecord, onclause=col(GroupMemberRecord.group_id) == col(GroupRecord.id))
                .where(col(GroupMemberRecord.user_id) == member)
                .order_by(col(GroupRecord.name))
            )
            return [_to_group(one) for one in found.all()]


class JoinRequestRepository:
    """`group_join_requests` 表的读写。

    Args:
        engine: 到 Postgres 的异步引擎。
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def create(self, *, group_id: str, user_id: str) -> JoinRequest | None:
        """发起一条入组申请。

        Args:
            group_id: 目标组，调用方应先确认它存在。
            user_id: 申请人。

        Returns:
            新建的申请；**已经挂着一条待审批时返回 None** —— 那是条件唯一索引挡下的，
            不是失败，连点两次只该留下一条待办。
        """
        identifier, applicant = _parse(group_id), _parse(user_id)
        if identifier is None or applicant is None:
            return None
        record = JoinRequestRecord(
            id=uuid4(),
            group_id=identifier,
            user_id=applicant,
            status=JoinRequestStatus.PENDING,
            created_at=datetime.now(UTC),
        )
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            session.add(record)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                return None
        return _to_request(record)

    async def get(self, request_id: str) -> JoinRequest | None:
        """按 id 查一条申请。

        Args:
            request_id: 申请标识。

        Returns:
            找到的申请，否则 None。端点据此确认「这条申请是不是我那个组的」。
        """
        identifier = _parse(request_id)
        if identifier is None:
            return None
        async with AsyncSession(self._engine) as session:
            record = await session.get(JoinRequestRecord, identifier)
        return None if record is None else _to_request(record)

    async def decide(self, request_id: str, *, approved: bool) -> bool:
        """批准或否决一条申请。

        **批准与入组写在同一个事务里**：分成两步的话，中间失败会留下「批了却没进组」，
        而那种半成品状态从两边看都是正常的 —— 申请是已批准，名册上没有这个人。

        **状态是条件更新而不是「先读再写」**：两个标签页各点一次时，先读再写的那一份
        会让第二次把否决改成批准。

        Args:
            request_id: 申请标识。
            approved: 批准还是否决。

        Returns:
            这一次是否真的改动了。已经处理过的申请返回 False。
        """
        identifier = _parse(request_id)
        if identifier is None:
            return False
        statement = (
            update(JoinRequestRecord)
            .where(
                col(JoinRequestRecord.id) == identifier,
                col(JoinRequestRecord.status) == JoinRequestStatus.PENDING,
            )
            .values(
                status=JoinRequestStatus.APPROVED if approved else JoinRequestStatus.REJECTED,
                decided_at=datetime.now(UTC),
            )
            .returning(col(JoinRequestRecord.group_id), col(JoinRequestRecord.user_id))
        )
        async with self._engine.begin() as connection:
            decided = (await connection.execute(statement)).first()
            if decided is None:
                return False
            if approved:
                await connection.execute(
                    insert(GroupMemberRecord).values(group_id=decided[0], user_id=decided[1]).on_conflict_do_nothing()
                )
        logger.info("审批入组：request_id=%s approved=%s", request_id, approved)
        return True

    async def list_pending(self, group_id: str) -> list[JoinRequestDetail]:
        """一个组还没处理的申请，**先申请的排前面**。

        Args:
            group_id: 组标识。

        Returns:
            待审批的申请；没有则空列表。
        """
        identifier = _parse(group_id)
        if identifier is None:
            return []
        statement = (
            _detail_select()
            .where(
                col(JoinRequestRecord.group_id) == identifier,
                col(JoinRequestRecord.status) == JoinRequestStatus.PENDING,
            )
            .order_by(col(JoinRequestRecord.created_at))
        )
        return await self._detail(statement)

    async def list_for_user(self, user_id: str) -> list[JoinRequestDetail]:
        """一个人发起过的全部申请，最近的排前面。

        **已决策的也在里面**：只留待审批的话，学生看到申请消失，分不清是被否决了
        还是自己没点成功。

        Args:
            user_id: 申请人。

        Returns:
            这个人的申请；没有则空列表。
        """
        applicant = _parse(user_id)
        if applicant is None:
            return []
        statement = (
            _detail_select()
            .where(col(JoinRequestRecord.user_id) == applicant)
            .order_by(col(JoinRequestRecord.created_at).desc())
        )
        return await self._detail(statement)

    async def _detail(self, statement: Select[DetailRow]) -> list[JoinRequestDetail]:
        async with self._engine.connect() as connection:
            found = (await connection.execute(statement)).all()
        return [
            JoinRequestDetail(
                id=row[0].hex,
                group_id=row[1].hex,
                group_name=row[2],
                user_id=row[3].hex,
                user_name=row[4],
                status=row[5],
                created_at=row[6],
            )
            for row in found
        ]


def _detail_select() -> Select[DetailRow]:
    """申请连同两头的名字。七列，因此走连接而不是 `session.exec` —— 后者最多认四列。"""
    return (
        sa_select(
            col(JoinRequestRecord.id),
            col(JoinRequestRecord.group_id),
            col(GroupRecord.name),
            col(JoinRequestRecord.user_id),
            col(UserRecord.name),
            col(JoinRequestRecord.status),
            col(JoinRequestRecord.created_at),
        )
        .join(GroupRecord, onclause=col(GroupRecord.id) == col(JoinRequestRecord.group_id))
        .join(UserRecord, onclause=col(UserRecord.id) == col(JoinRequestRecord.user_id))
    )


def _to_group(record: GroupRecord) -> Group:
    return Group(
        id=record.id.hex,
        name=record.name,
        owner_id=record.owner_id.hex,
        invite_code=record.invite_code,
    )


def _to_request(record: JoinRequestRecord) -> JoinRequest:
    return JoinRequest(
        id=record.id.hex,
        group_id=record.group_id.hex,
        user_id=record.user_id.hex,
        status=record.status,
        created_at=record.created_at,
    )


def _parse(identifier: str) -> UUID | None:
    """标识来自 URL 与 session，解析不了就是「查不到」，不是 500。"""
    try:
        return UUID(identifier)
    except ValueError:
        return None
