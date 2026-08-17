"""课题组的数据形状：`groups` / `user_groups` / `group_join_requests` 三张表。

**组是名册与准入，不是权限边界。** 进了组不会因此多看见任何东西 —— 会话、上传数据、
产物仍然只有主人自己看得到，与组无关。组做两件事：给注册发一张门票（邀请码），
以及让教师知道自己带的是哪些人。把它扩成「组内可见」要动的是数据访问层，
不是这三张表，那时才该重新论证。

**组主是 `groups.owner_id` 一列，不是一套组内角色。** 谁能加人、移人、批申请，
只看是不是这一列上的那个人；组内其余成员之间没有任何级别差异。用一列换掉一张
「组内角色」表，是因为当前唯一需要区分的就是「组主 / 非组主」这一刀。

`invite_code` 与 `groups.name` 都是全库唯一的：前者撞码等于把学生发进别人的组，
后者重名会让学生在浏览列表里没法分辨该申请哪一个。
"""

import secrets
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Column, Enum, Index, text
from sqlmodel import Field, SQLModel

TABLE_NAME = "groups"
MEMBER_TABLE_NAME = "user_groups"
REQUEST_TABLE_NAME = "group_join_requests"

MEMBER_GROUP_INDEX = "ix_user_groups_group"
PENDING_REQUEST_INDEX = "ux_group_join_requests_pending"

# 唯一约束只盖 pending 那一段：被否决之后还能再申请，否则一次否决就是永久拉黑
PENDING_REQUEST_CONDITION = "status = 'pending'"

# 邀请码的长度与字母表。**去掉 0/O/1/I**：这串东西要被教师抄在黑板上或发在群里、
# 由学生手打进注册框，形近字符换来的每一次「码不对」都得人来排查
INVITE_CODE_LENGTH = 8
INVITE_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class JoinRequestStatus(StrEnum):
    """入组申请的状态。"""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


def status_column() -> Column[Enum]:
    """状态列，**按枚举的值存而不是按名字**，与 `users.role` 同一个理由。"""
    return Column(
        Enum(
            JoinRequestStatus,
            values_callable=lambda enum: [one.value for one in enum],
            native_enum=False,
        ),
        nullable=False,
    )


def new_invite_code() -> str:
    """随机生成一个邀请码。

    **用 `secrets` 而不是 `random`**：这串东西是准入凭证，可预测的序列等于谁都能
    猜出一个有效的码把自己塞进组里。

    Returns:
        一个由无歧义大写字母与数字组成的短码。
    """
    return "".join(secrets.choice(INVITE_CODE_ALPHABET) for _ in range(INVITE_CODE_LENGTH))


class GroupRecord(SQLModel, table=True):
    """`groups` 表的一行。"""

    __tablename__ = TABLE_NAME

    id: UUID = Field(primary_key=True)
    name: str = Field(unique=True)
    owner_id: UUID = Field(index=False, foreign_key="users.id")
    invite_code: str = Field(unique=True)
    created_at: datetime


class GroupMemberRecord(SQLModel, table=True):
    """`user_groups` 表的一行：一个人属于一个组。

    复合主键顺序是 `(user_id, group_id)`，因此「我在哪些组」这一问由主键直接覆盖；
    反方向「这个组有谁」另配一条索引 —— 名册页每次打开都要走它。
    """

    __tablename__ = MEMBER_TABLE_NAME
    __table_args__ = (Index(MEMBER_GROUP_INDEX, "group_id"),)

    user_id: UUID = Field(primary_key=True, index=False, foreign_key="users.id")
    group_id: UUID = Field(primary_key=True, index=False, foreign_key="groups.id")


class JoinRequestRecord(SQLModel, table=True):
    """`group_join_requests` 表的一行。

    已决策的申请不删，留着是为了回答「我上次申请被否了没」—— 删掉的话学生只看到
    申请消失，分不清是被否决还是自己没点成功。
    """

    __tablename__ = REQUEST_TABLE_NAME
    __table_args__ = (
        Index(
            PENDING_REQUEST_INDEX,
            "group_id",
            "user_id",
            unique=True,
            postgresql_where=text(PENDING_REQUEST_CONDITION),
        ),
    )

    id: UUID = Field(primary_key=True)
    group_id: UUID = Field(index=False, foreign_key="groups.id")
    user_id: UUID = Field(index=False, foreign_key="users.id")
    status: JoinRequestStatus = Field(sa_column=status_column())
    created_at: datetime
    decided_at: datetime | None = Field(default=None)
