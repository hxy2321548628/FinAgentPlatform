"""broker 内部 API 的请求与响应模型。

**这不是对外契约**：只有 api 进程会调 broker，两边同一个仓库同一次部署，
因此这里可以随实现演进，不像事件契约那样要照顾前端。

字节走 base64 而不是 multipart：上传与产物都是一次性的整块数据，
JSON 里带一个字段比拼多段报文简单，而这条链路是本机回环，编码开销无所谓。
"""

from datetime import datetime

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


class StoreSkillFile(BaseModel):
    """一版 Skill 中的一个已校验文件。"""

    path: str = Field(min_length=1, description="相对于 Skill 根目录的 POSIX 路径")
    content: Base64Bytes = Field(description="文件内容")


class StoreSkillVersionRequest(BaseModel):
    """把一版 Skill 持久化到宿主机仓库。"""

    files: list[StoreSkillFile] = Field(min_length=1, description="已通过上传校验的文件清单")


class AlignSkillReference(BaseModel):
    """run 快照里冻结的一版 Skill。"""

    skill_id: str = Field(min_length=1, description="Skill 标识")
    version: int = Field(ge=1, description="版本号")
    name: str = Field(min_length=1, description="物化目录名")


class AlignSkillsRequest(BaseModel):
    """一次 run 开跑前需要物化的完整 Skill 清单。"""

    skills: list[AlignSkillReference] = Field(description="完整清单，清单外内容会删除")


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
    directory: str = Field(
        default="",
        description="落到会话目录下的哪个子目录，相对会话根。留空即根下；**必须已存在**",
    )


class SaveResponse(BaseModel):
    """落盘结果。"""

    filename: str = Field(min_length=1, description="落盘后的文件名，可能与上传时不同")
    size: int = Field(ge=0, description="字节数")
    path: str = Field(min_length=1, description="落盘后相对会话根的路径，前端拿它去预览或下载")


class TreeEntryItem(BaseModel):
    """会话工作目录里的一个条目。"""

    path: str = Field(min_length=1, description="相对会话根的路径，posix 分隔")
    is_dir: bool = Field(description="是不是目录")
    size: int = Field(ge=0, description="字节数，目录的值没有意义")
    modified_at: datetime = Field(description="最后修改时间，UTC")


class TreeResponse(BaseModel):
    """一个会话工作目录的全部条目。"""

    entries: list[TreeEntryItem] = Field(description="按路径排序，父目录排在它的子项之前")
    truncated: bool = Field(description="条目太多被砍过，给的只是其中一批")


class PreviewResponse(BaseModel):
    """一个文件的一段文本内容。"""

    text: str = Field(description="窗口内的文本。二进制文件为空")
    total_line: int = Field(ge=0, description="读到的总行数。truncated 为真时只是开头那一截的行数")
    start_line: int = Field(ge=0, description="窗口首行，1-indexed。窗口为空时是 0")
    end_line: int = Field(ge=0, description="窗口末行，1-indexed。窗口为空时是 0")
    is_binary: bool = Field(description="不是文本，调用方该改走原始字节那条路")
    truncated: bool = Field(description="文件比字节上限长，后面还有没读的")


class FileStatResponse(BaseModel):
    """一个文件的元信息，不含字节。"""

    path: str = Field(
        min_length=1,
        description="规范化后相对会话根的路径。调用方拿它拼下游的内部跳转，因此不能是请求里那个原样的串",
    )
    size: int = Field(ge=0, description="字节数")
    mime: str = Field(min_length=1, description="按扩展名猜的内容类型")


class QueuedData(BaseModel):
    """排队中，附当前排位。"""

    position: int = Field(ge=1, description="当前排位")


class AcquireErrorData(BaseModel):
    """申请沙箱失败。"""

    code: RunErrorCode = Field(description="失败原因")
    message: str = Field(min_length=1, description="中文说明")
