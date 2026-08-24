"""提交时冻结、可安全交给模型的用户信息。"""

from pydantic import BaseModel, ConfigDict, Field

from app.user.model import UserRole


class UserContext(BaseModel):
    """不含邮箱、用户 ID 与凭据的运行快照。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, description="姓名或用户名")
    role: UserRole = Field(description="平台角色")
    dept: str = Field(default="", description="院系")
    token_used_today: int = Field(default=0, ge=0, description="提交时今日已用 token 当量")
    token_limit_daily: int | None = Field(default=None, ge=0, description="每日上限；空表示不限")
    active_runs: int = Field(default=0, ge=0, description="提交时活跃分析数")
    concurrent_run_limit: int = Field(ge=1, description="并发分析上限")
