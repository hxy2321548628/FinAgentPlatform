"""对外接口的请求与响应模型。

只放 HTTP 层自己的形状。**事件不在这里** —— 那是前后端共用的契约，
定义在事件包里，SSE 直接把它序列化出去。
"""

from pydantic import BaseModel, Field

from event.model import RunStatus
from run.decision import Decision
from user.model import UserRole


class LoginRequest(BaseModel):
    """登录。"""

    name: str = Field(min_length=1, description="用户名")
    password: str = Field(min_length=1, description="口令。只用于校验，不落库也不进日志")


class MeResponse(BaseModel):
    """当前登录用户。

    **不含「所属组」**：`groups` 两张表本期不建，组内共享资源也一样没有 ——
    返回一个恒为空的字段只会让前端以为它将来会有东西。
    """

    id: str = Field(min_length=1, description="用户标识")
    name: str = Field(min_length=1, description="用户名")
    role: UserRole = Field(description="角色，前端据此决定是否显示管理入口")


class ApproveRequest(BaseModel):
    """审批回传。

    每个待确认的调用回一个决策，**用显式 `index` 而不是依赖数组顺序** ——
    缺失或重复的 index 一律 `VALIDATION_ERROR`。
    """

    decisions: list[Decision] = Field(min_length=1, description="教师的决策，每个待确认调用一个")


class ThreadResponse(BaseModel):
    """新建会话的响应。"""

    id: str = Field(min_length=1, description="会话标识，后续所有操作都带它")


class UploadResponse(BaseModel):
    """上传文件的响应。"""

    filename: str = Field(min_length=1, description="落盘后的文件名，可能与上传时不同")
    size: int = Field(ge=0, description="字节数")


class RunRequest(BaseModel):
    """提交一次分析。"""

    content: str = Field(min_length=1, description="教师的问题")


class RunResponse(BaseModel):
    """run 的详情。"""

    id: str = Field(min_length=1, description="run 标识")
    thread_id: str = Field(min_length=1, description="所属会话")
    status: RunStatus = Field(description="当前状态")
