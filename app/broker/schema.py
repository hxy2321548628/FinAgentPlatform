"""broker 内部 API 的请求与响应模型。

**这不是对外契约**：只有 api 进程会调 broker，两边同一个仓库同一次部署，
因此这里可以随实现演进，不像事件契约那样要照顾前端。

字节走 base64 而不是 multipart：上传与产物都是一次性的整块数据，
JSON 里带一个字段比拼多段报文简单，而这条链路是本机回环，编码开销无所谓。
"""

from pydantic import Base64Bytes, BaseModel, Field

from event.model import RunErrorCode

# P3 的工具幂等键（ADR-0014）。本期**不实现去重**，但参数位现在就留出来 ——
# 等 P3 再加就是一次协议变更，两边都得改。
IDEMPOTENCY_FIELD = Field(
    default=None,
    description="幂等键，P3 用它在 broker 侧做写操作去重。本期只接收不使用",
)


class ToolRequest(BaseModel):
    """所有工具请求的公共部分。"""

    checkpoint_ns: str | None = IDEMPOTENCY_FIELD


class LsRequest(ToolRequest):
    """列目录。"""

    path: str = Field(description="agent 视角的目录路径")


class ReadRequest(ToolRequest):
    """读文件的一段。"""

    file_path: str = Field(description="agent 视角的文件路径")
    offset: int = Field(default=0, ge=0, description="起始行")
    limit: int = Field(default=2000, ge=1, description="最多读多少行")


class WriteRequest(ToolRequest):
    """写文件，已存在则覆盖。"""

    file_path: str = Field(description="agent 视角的文件路径")
    content: str = Field(description="文件内容")


class EditRequest(ToolRequest):
    """替换文件里的字符串。"""

    file_path: str = Field(description="agent 视角的文件路径")
    old_string: str = Field(description="被替换的串")
    new_string: str = Field(description="替换成什么")
    replace_all: bool = Field(default=False, description="替换全部还是只替换第一处")


class DeleteRequest(ToolRequest):
    """删除文件。"""

    file_path: str = Field(description="agent 视角的文件路径")


class GlobRequest(ToolRequest):
    """按通配符找文件。"""

    pattern: str = Field(description="通配符")
    path: str | None = Field(default=None, description="搜索起点，不给就是整个 workspace")


class GrepRequest(ToolRequest):
    """在文件内容里找字面串。"""

    pattern: str = Field(description="要找的字面串")
    path: str | None = Field(default=None, description="搜索起点，不给就是整个 workspace")
    glob: str | None = Field(default=None, description="只搜匹配这个通配符的文件")
    max_count: int | None = Field(default=None, ge=1, description="每个文件最多报几处")


class ExecuteRequest(ToolRequest):
    """在沙箱容器里执行命令。"""

    command: str = Field(description="完整的 shell 命令串")
    timeout: int | None = Field(default=None, ge=1, description="超时秒数，不给则用默认值")


class UploadItem(BaseModel):
    """一个待上传的文件。"""

    path: str = Field(description="agent 视角的目标路径")
    content: Base64Bytes = Field(description="文件内容")


class UploadRequest(ToolRequest):
    """批量把字节写进 workspace。"""

    files: list[UploadItem] = Field(description="待上传的文件")


class DownloadRequest(ToolRequest):
    """批量从 workspace 取字节。"""

    paths: list[str] = Field(description="agent 视角的文件路径")


class FileResult(BaseModel):
    """一个文件的处理结果。批量操作允许部分成功，因此逐个带 error。"""

    path: str = Field(description="请求时给的路径")
    error: str | None = Field(default=None, description="出错原因，成功时为空")


class UploadResponse(BaseModel):
    """批量写字节的结果。"""

    files: list[FileResult] = Field(description="逐个文件的结果，顺序与请求一致")


class DownloadItem(BaseModel):
    """取回的一个文件。批量操作允许部分成功，因此逐个带 error。

    出方向的字节自己编码成 base64 字符串，不用 `Base64Bytes`：那个类型是给**入**方向
    准备的（校验时把 base64 解成 bytes），拿原始字节去构造它会当场解码失败。
    """

    path: str = Field(description="请求时给的路径")
    content: str | None = Field(default=None, description="base64 编码的文件内容，出错时为空")
    error: str | None = Field(default=None, description="出错原因")


class DownloadResponse(BaseModel):
    """批量取字节的结果。"""

    files: list[DownloadItem] = Field(description="逐个文件的结果，顺序与请求一致")


class AcquireRequest(BaseModel):
    """申请沙箱。"""

    holder: str = Field(
        min_length=1,
        description="谁在用。取 run 标识 —— 崩溃恢复接着跑的是同一个 run，因此重复申请是幂等的",
    )


class CreateThreadRequest(BaseModel):
    """给一个已经落表的会话建目录。"""

    thread_id: str = Field(min_length=1, description="会话标识，由 api 那边发号（threads 表是权威）")


class ThreadResponse(BaseModel):
    """新建会话的结果。"""

    thread_id: str = Field(min_length=1, description="会话标识")


class ExistsResponse(BaseModel):
    """会话是否存在。"""

    exists: bool = Field(description="目录在不在")


class SaveRequest(BaseModel):
    """把上传的文件落进会话目录。"""

    filename: str = Field(description="上传时带的文件名，不可信")
    content: Base64Bytes = Field(description="文件内容")


class SaveResponse(BaseModel):
    """落盘结果。"""

    filename: str = Field(min_length=1, description="落盘后的文件名，可能与上传时不同")
    size: int = Field(ge=0, description="字节数")


class ArtifactListResponse(BaseModel):
    """一次 run 产出的产物。"""

    artifacts: list[str] = Field(description="产物标识，形如 {thread_id}/{outputs 下的相对路径}")


class QueuedData(BaseModel):
    """排队中，附当前排位。"""

    position: int = Field(ge=1, description="当前排位")


class AcquireErrorData(BaseModel):
    """申请沙箱失败。"""

    code: RunErrorCode = Field(description="失败原因")
    message: str = Field(min_length=1, description="中文说明")
