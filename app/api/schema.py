"""对外接口的请求与响应模型。

只放 HTTP 层自己的形状。**事件不在这里** —— 那是前后端共用的契约，
定义在事件包里，SSE 直接把它序列化出去。
"""

from pydantic import BaseModel, Field

from event.model import RunStatus


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
