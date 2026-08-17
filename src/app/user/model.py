"""用户的数据形状：`users` 表的结构与角色枚举。

**四种角色里 `teacher` 与 `student` 权限完全相同**，二者唯一的实质差别是配额档位。
把它们分成两个角色而不是合成一个「普通用户」，就是为了配额能按角色分级 —— 学生人数
通常远多于教师，配额若相同，成本结构会由学生侧主导。

**管理员不是「能看一切的人」**：它多的只是账号与配额的管理能力，会话内容与上传数据
仍然只看得到自己的。这条边界落在数据访问层，不做成「绕过过滤」的旁路 ——
那种旁路一旦开出来就很难再收回去。

**课题组不在这里，也不影响这里。** 组是名册与准入（见 `group/model.py`），
`role` 与它无关：谁能管一个组只看 `groups.owner_id`，而不是看角色。
"""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Column, Enum
from sqlmodel import Field, SQLModel

TABLE_NAME = "users"

# 邮箱唯一索引。**它是第二把登录钥匙**，重了就分不清进来的是谁
EMAIL_INDEX = "ix_users_email"


class UserRole(StrEnum):
    """用户角色。

    **`reviewer` 只能看审核队列与通过 / 拒绝，别的一样都没有。** 一旦让它顺手多拿一样
    （比如「顺便能看看账号列表」），这个角色就退化成 `admin` 的别名，而设它的全部意义
    正是把「决定什么能进平台目录」这一件事交出去，同时不交出账号与配额。

    **三类资源一视同仁**（agent、skill、MCP，2026-08-16 起）：它们要判的是同一件事 ——
    这份东西该不该让全平台用。而 MCP 的启停与探活仍归 admin：那是运维，改的是一个
    已放行的服务此刻通不通，与「该不该放行」无关。

    **它不需要迁移**：`role` 列是 `native_enum=False` 存 varchar，多一个取值只是多一种
    字符串。但枚举这里必须先认得它，否则 `/auth/me` 序列化当场抛。
    """

    ADMIN = "admin"
    REVIEWER = "reviewer"
    TEACHER = "teacher"
    STUDENT = "student"


def role_column() -> Column[Enum]:
    """角色列，**按枚举的值存而不是按名字**。

    默认行为是存名字，于是库里躺着的是 `ADMIN` 而架构文档写的是 `admin` ——
    两边对不上时不报错，只是所有照文档写的 SQL 都查不到东西。
    """
    return Column(
        Enum(UserRole, values_callable=lambda enum: [one.value for one in enum], native_enum=False),
        nullable=False,
    )


class UserRecord(SQLModel, table=True):
    """`users` 表的一行。"""

    __tablename__ = TABLE_NAME

    id: UUID = Field(primary_key=True)
    name: str = Field(unique=True)
    # **登录认它也认 `name`**（P11）。两把钥匙开同一把锁，因此它同样要全库唯一 ——
    # 重了的话「这个邮箱是谁」就没有唯一答案，而那正是登录要回答的问题
    email: str = Field(unique=True)
    # 院系。**不参与任何判断**，只是名册上的一列，因此不设唯一也不设索引
    dept: str = Field(default="")
    password_hash: str
    role: UserRole = Field(sa_column=role_column())
    # **留空表示「跟着角色的默认档走」**，不是「没有配额」。默认档在 Settings 里，
    # 因此调一次配置就对所有没被单独调整过的人生效；而把默认值在建号时写死进行里，
    # 改配置就只影响之后新建的账号 —— 本期没有管理接口，那等于永远改不动
    quota_tokens_daily: int | None = Field(default=None)
    quota_concurrent_runs: int | None = Field(default=None)
    is_active: bool = Field(default=True)
    created_at: datetime
