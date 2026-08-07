"""用户的数据形状：`users` 表的结构与角色枚举。

**三种角色里 `teacher` 与 `student` 权限完全相同**，二者唯一的实质差别是配额档位。
把它们分成两个角色而不是合成一个「普通用户」，就是为了配额能按角色分级 —— 学生人数
通常远多于教师，配额若相同，成本结构会由学生侧主导。

**管理员不是「能看一切的人」**：它多的只是账号与配额的管理能力，会话内容与上传数据
仍然只看得到自己的。这条边界落在数据访问层，不做成「绕过过滤」的旁路 ——
那种旁路一旦开出来就很难再收回去。

`groups` / `user_groups` 两张表不建：没有任何组内共享资源挂在上面，现在猜它们的字段
与将来照实际需求建表成本相同，但猜错要迁移。
"""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Column, Enum
from sqlmodel import Field, SQLModel

TABLE_NAME = "users"


class UserRole(StrEnum):
    """用户角色。"""

    ADMIN = "admin"
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
    password_hash: str
    role: UserRole = Field(sa_column=role_column())
    # **留空表示「跟着角色的默认档走」**，不是「没有配额」。默认档在 Settings 里，
    # 因此调一次配置就对所有没被单独调整过的人生效；而把默认值在建号时写死进行里，
    # 改配置就只影响之后新建的账号 —— 本期没有管理接口，那等于永远改不动
    quota_tokens_daily: int | None = Field(default=None)
    quota_concurrent_runs: int | None = Field(default=None)
    is_active: bool = Field(default=True)
    created_at: datetime
