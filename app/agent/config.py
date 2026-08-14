"""Agent 在一次 run 内实际生效的配置。"""

from pydantic import BaseModel, ConfigDict, Field

MAX_SYSTEM_PROMPT_LENGTH = 4000


class AgentConfig(BaseModel):
    """一次 run 的配置快照。

    未知字段当场拒绝，避免配置写错后只是静默不生效。
    """

    model_config = ConfigDict(extra="forbid")

    system_prompt: str | None = Field(
        default=None,
        max_length=MAX_SYSTEM_PROMPT_LENGTH,
        description="用户自定义的角色段；为空则用平台默认角色",
    )
