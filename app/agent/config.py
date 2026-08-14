"""Agent 在一次 run 内实际生效的配置。

**两个形状，分在提交前后。** 教师给的那一份（`AgentConfigRequest`）里
「自己写提示词」与「引用一个平台上的 agent」互斥 —— 同时给两样时，哪一样生效
只能靠约定，而约定错了的表现是「今天这个 agent 好像不太灵」，不报错。
提交那一刻引用被解析掉，落进 `runs` 的快照（`AgentConfig`）里：agent 引用冻结
具体版本与提示词，Skill 引用冻结具体版本与名称。

**执行侧不再解析目录引用。** 装配层只读快照：提示词直接使用，Skill 由 worker
按冻结版本物化进沙箱。
"""

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_SYSTEM_PROMPT_LENGTH = 4000

EXCLUSIVE_MESSAGE = "「选一个智能体」与「自己写提示词」只能二选一"


class SkillReference(BaseModel):
    """一次 run 快照里冻结的一版 Skill。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    skill_id: str = Field(min_length=1, description="Skill 的稳定标识")
    version: int = Field(ge=1, description="提交时解析出的已发布版本")
    name: str = Field(min_length=1, description="物化到 workspace 时使用的目录名")


class AgentConfig(BaseModel):
    """一次 run 的配置快照。

    未知字段当场拒绝，避免配置写错后只是静默不生效。

    **这里不校验互斥**：快照本来就同时带着引用与它解析出来的提示词。互斥是给
    使用者那一侧的规矩，落在 `AgentConfigRequest` 上。
    """

    model_config = ConfigDict(extra="forbid")

    system_prompt: str | None = Field(
        default=None,
        max_length=MAX_SYSTEM_PROMPT_LENGTH,
        description="用户自定义的角色段；为空则用平台默认角色",
    )
    agent_id: str | None = Field(
        default=None,
        description="引用的平台智能体；为空表示这一轮没有引用任何 agent",
    )
    agent_version: int | None = Field(
        default=None,
        ge=1,
        description="**引用被冻结在哪一版**。作者之后再发新版本，这条 run 的快照仍指着这一版",
    )
    skills: list[SkillReference] | None = Field(
        default=None,
        description="提交时解析并冻结的 Skill 版本；为空表示这一轮没有挂 Skill",
    )


class AgentConfigRequest(BaseModel):
    """教师给的那一份配置。

    **两条路互斥**：引用一个 agent，或者自己写一段提示词。同时给一律 422 ——
    静默挑一个的话，教师看到的是「我明明选了 agent，怎么没生效」。
    """

    model_config = ConfigDict(extra="forbid")

    system_prompt: str | None = Field(
        default=None,
        max_length=MAX_SYSTEM_PROMPT_LENGTH,
        description="自己写的角色段；为空则用平台默认角色",
    )
    agent_id: str | None = Field(
        default=None,
        description="要引用的平台智能体。**提交那一刻解析成具体版本**，解析不出来一律 422",
    )
    skills: list[str] | None = Field(
        default=None,
        description="这一轮要挂的 Skill 标识；提交时按当前用户可见性解析",
    )

    @field_validator("skills", mode="after")
    @classmethod
    def _omit_an_empty_skill_list(cls, value: list[str] | None) -> list[str] | None:
        """空选择按未挂 Skill 处理，避免快照多出无意义的空键。"""
        return value or None

    @model_validator(mode="after")
    def _only_one_source(self) -> Self:
        """两条路只能走一条。"""
        if self.agent_id is not None and self.system_prompt is not None:
            raise ValueError(EXCLUSIVE_MESSAGE)
        return self


def effective_config(
    *,
    thread_config: dict[str, object] | None,
    override: AgentConfigRequest | None,
) -> AgentConfigRequest:
    """算出这一轮实际生效的配置，**引用还没解析**。

    `override` 为 `None` 表示这一轮没覆盖，显式的空对象则是整块覆盖为平台默认 ——
    不能写成「有就用、没有就取会话的」，那会把这两种语义合并成一种。

    Args:
        thread_config: 会话的默认配置，直接来自库里那一块 JSON。
        override: 这一轮的整块覆盖；不传则继承会话默认。

    Returns:
        这一轮生效的配置。

    Raises:
        ValidationError: 会话默认里有已经不支持的键。**不能当成空配置放过** ——
            那会让一个配错的会话安静地按平台默认跑下去。
    """
    if override is not None:
        return override
    return AgentConfigRequest.model_validate({} if thread_config is None else thread_config)
