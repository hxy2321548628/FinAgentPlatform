"""预置智能体的数据形状：`agents` / `agent_versions` / `reviews` / `resource_groups` 四张表。

**这个包与 `agent/` 是两件事。** `agent/` 是装配层 —— 把一次 run 的配置拼成可执行的
图；这里是目录层 —— 谁写了什么、共享给了谁、审没审过。塞进同一个包会让它同时承担
两个职责，而两者的变更节奏完全不同：装配层跟着模型能力走，目录层跟着组织流程走。

**「定稿」与「过审」是两个互不蕴含的维度，因此落在两张表上。**
`agent_versions.status` 只说作者定没定稿；平台目录的准入记在 `reviews` 里，一个版本
一条。合成一个枚举表达不了「被拒但组内照常可用」这一种状态 —— `rejected` 一旦盖在
版本行上，就说不清它对组内还算不算数。

**三档可见性在库里不是一个三值枚举**：前两档（私有 / 组内）是作者的开关，落在
`agents.visibility` 上；第三档（平台目录）要 reviewer 点头，由「有一个版本 approved」
决定。把它塞进同一个枚举会开出一条不该存在的状态转移 —— 作者把自己的东西改成
「平台目录」。

**版本行只追加不原地改。** 已发布的版本永远留着：落进 run 快照的引用要照常读得回来，
而作者改一次内容就是追加下一个版本号的新草稿。
"""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Column, Enum, Index, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

TABLE_NAME = "agents"
VERSION_TABLE_NAME = "agent_versions"
REVIEW_TABLE_NAME = "reviews"
RESOURCE_GROUP_TABLE_NAME = "resource_groups"

AGENT_NAME_INDEX = "ux_agents_owner_name"
AGENT_OWNER_INDEX = "ix_agents_owner"
VERSION_NUMBER_INDEX = "ux_agent_versions_number"
DRAFT_VERSION_INDEX = "ux_agent_versions_draft"
PENDING_REVIEW_INDEX = "ux_reviews_pending"
REVIEW_TARGET_INDEX = "ix_reviews_target"

# 重名只在**没被删掉的**那些之间算数。全表唯一的话，作者删掉一个 agent 之后
# 再也用不回同一个名字 —— 而软删的行只有他自己在「我的」里看得到
AGENT_NAME_CONDITION = "is_deleted = false"

# 一个 agent 同时最多挂一个草稿。多个草稿意味着「我在改的是哪一份」没有答案
DRAFT_VERSION_CONDITION = "status = 'draft'"

# 一个版本同时最多一条待审。连点两次提审只该在 reviewer 的队列里留下一条
PENDING_REVIEW_CONDITION = "status = 'pending'"

# 第一个版本号。从 1 起而不是 0 —— 这个数字要显示给老师看（「v1」「v2」）
FIRST_VERSION = 1


class Visibility(StrEnum):
    """作者能拨的那两档可见性。

    **平台目录不在这里** —— 它由 `reviews` 决定，不是作者说了算的开关。
    """

    PRIVATE = "private"
    GROUP = "group"


class VersionStatus(StrEnum):
    """一个版本定没定稿。"""

    DRAFT = "draft"
    RELEASED = "released"


class ReviewStatus(StrEnum):
    """一条审核记录的状态。"""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ResourceKind(StrEnum):
    """能被共享与被审核的资源种类。

    Skill 与智能体复用同一套共享与审核流程；表结构不因资源种类增加而变化。

    **MCP 只复用审核那一半。** 它不进 `resource_groups` —— 目录是平台级的，管理员
    放行了就人人可勾，没有三档可见性；它的审核也不进 reviewer 的队列，见
    `REVIEWABLE_KIND`。
    """

    AGENT = "agent"
    SKILL = "skill"
    MCP = "mcp"


# 统一审核队列里出现的那些。**MCP 不在其中，这不是遗漏，也不是权限问题** ——
# reviewer 2026-08-16 起审得了 MCP，但它有自己那一页（`/api/mcp/admin`），
# 上面带着申请人、失败计数与探活结果，那些在统一队列里表达不了。
# 两个入口同时列同一批申请只会让两边的状态看起来不一致。
REVIEWABLE_KIND: tuple[ResourceKind, ...] = (ResourceKind.AGENT, ResourceKind.SKILL)


def _value_enum(enum: type[StrEnum], *, primary_key: bool = False) -> Column[Enum]:
    """枚举列，**按枚举的值存而不是按名字**，与 `users.role` 同一个理由。

    默认行为是存名字，于是库里躺着的是 `DRAFT` 而文档写的是 `draft` ——
    两边对不上时不报错，只是所有照文档写的 SQL 都查不到东西。

    Args:
        enum: 枚举类型。
        primary_key: 这一列是不是主键的一部分。**给了 `sa_column` 之后 `Field`
            上的 `primary_key` 就不再生效**，只能标在列本身上。

    Returns:
        可交给 `sa_column` 的列定义。
    """
    return Column(
        Enum(enum, values_callable=lambda one: [each.value for each in one], native_enum=False),
        nullable=False,
        primary_key=primary_key,
    )


class AgentRecord(SQLModel, table=True):
    """`agents` 表的一行：一个智能体的身份，不含内容。

    内容全部在版本行上。分开是因为改名与改提示词是两件事 —— 前者不该产生新版本，
    后者必须产生。
    """

    __tablename__ = TABLE_NAME
    __table_args__ = (
        Index(AGENT_OWNER_INDEX, "owner_id"),
        Index(
            AGENT_NAME_INDEX,
            "owner_id",
            "name",
            unique=True,
            postgresql_where=text(AGENT_NAME_CONDITION),
        ),
    )

    id: UUID = Field(primary_key=True)
    owner_id: UUID = Field(index=False, foreign_key="users.id")
    # **同一作者名下唯一，不是全库唯一。** 全库唯一意味着谁先占了名字别人就不能用，
    # 而广场卡片本来就带着作者名
    name: str
    description: str = Field(default="")
    subject: str = Field(default="")
    visibility: Visibility = Field(sa_column=_value_enum(Visibility))
    # **不去重、不实时。** 它的用途是判断哪些资源值得平台收编，不是排行榜
    call_count: int = Field(default=0)
    # 软删：作者的「我的」里还看得到（能看出自己删过什么），别处一律当它不存在。
    # 硬删会撞上 run 快照里那个 agent_id —— 那是历史，删掉等于往账本里挖洞
    is_deleted: bool = Field(default=False)
    created_at: datetime
    updated_at: datetime


class AgentVersionRecord(SQLModel, table=True):
    """`agent_versions` 表的一行：一个版本的内容。

    提示词、Skill、子智能体与 MCP 引用在发布时一起冻结。**四者冻得住的东西不一样**：
    前三者冻的是内容（版本号 + 内容在平台手里），MCP 冻的只是 `{server_id, name}` ——
    那台校外机器明天返回什么，平台今天不知道。
    """

    __tablename__ = VERSION_TABLE_NAME
    __table_args__ = (
        Index(VERSION_NUMBER_INDEX, "agent_id", "version", unique=True),
        Index(
            DRAFT_VERSION_INDEX,
            "agent_id",
            unique=True,
            postgresql_where=text(DRAFT_VERSION_CONDITION),
        ),
    )

    id: UUID = Field(primary_key=True)
    agent_id: UUID = Field(index=False, foreign_key="agents.id")
    version: int
    status: VersionStatus = Field(sa_column=_value_enum(VersionStatus))
    system_prompt: str = Field(default="")
    skill_refs: list[dict[str, object]] | None = Field(default=None, sa_column=Column(JSONB, nullable=True))
    subagent_refs: list[dict[str, object]] | None = Field(default=None, sa_column=Column(JSONB, nullable=True))
    mcp_refs: list[dict[str, object]] | None = Field(default=None, sa_column=Column(JSONB, nullable=True))
    created_at: datetime
    # 发布那一刻。草稿为空 —— 广场按它排序，而没定稿的东西根本进不了广场
    released_at: datetime | None = Field(default=None)


class ReviewRecord(SQLModel, table=True):
    """`reviews` 表的一行：一次提审与它的结果。

    **`target_id` 指的是版本行，不是 agent 行。** 审核管的是「这一版能不能进广场」，
    盯着 agent 审的话，审过一次之后作者随便改 —— 那等于没有审核。
    """

    __tablename__ = REVIEW_TABLE_NAME
    __table_args__ = (
        Index(REVIEW_TARGET_INDEX, "target_kind", "target_id"),
        Index(
            PENDING_REVIEW_INDEX,
            "target_kind",
            "target_id",
            unique=True,
            postgresql_where=text(PENDING_REVIEW_CONDITION),
        ),
    )

    id: UUID = Field(primary_key=True)
    target_kind: ResourceKind = Field(sa_column=_value_enum(ResourceKind))
    target_id: UUID = Field(index=False)
    status: ReviewStatus = Field(sa_column=_value_enum(ReviewStatus))
    # 作者提审时勾的那一下：内容合规、后果自负。**后端也校验**，不能只靠前端 ——
    # 这一列存下来的是「他确实勾过」，出了事要拿它说话
    responsibility_confirmed: bool = Field(default=False)
    # 拒绝理由。通过时为空 —— 通过不需要解释，拒绝必须给作者一句能照着改的话
    reason: str | None = Field(default=None)
    submitted_by: UUID = Field(index=False, foreign_key="users.id")
    reviewed_by: UUID | None = Field(default=None, index=False, foreign_key="users.id")
    created_at: datetime
    decided_at: datetime | None = Field(default=None)


class ResourceGroupRecord(SQLModel, table=True):
    """`resource_groups` 表的一行：一个资源共享给了一个组。

    一个资源可以同时共享给多个组，因此是关联表而不是 `agents` 上的一列。
    """

    __tablename__ = RESOURCE_GROUP_TABLE_NAME

    resource_kind: ResourceKind = Field(sa_column=_value_enum(ResourceKind, primary_key=True))
    resource_id: UUID = Field(primary_key=True, index=False)
    group_id: UUID = Field(primary_key=True, index=False, foreign_key="groups.id")
