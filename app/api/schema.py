"""对外接口的请求与响应模型。

只放 HTTP 层自己的形状。**事件不在这里** —— 那是前后端共用的契约，
定义在事件包里，SSE 直接把它序列化出去。
"""

from datetime import date, datetime

from pydantic import BaseModel, Field

from event.model import RunStatus
from group.model import JoinRequestStatus
from run.decision import Decision
from user.model import UserRole

# 自助注册的口令下限。**登录不设这个下限**：那会把已有的短口令账号一次性锁在门外，
# 而它们的强度不会因为登录端点多一条校验而变好
MIN_PASSWORD_LENGTH = 8

# 用户名与组名的长度上限。库里这两列是不限长的 varchar，挡住超长输入的只有这里
MAX_NAME_LENGTH = 32


class LoginRequest(BaseModel):
    """登录。"""

    name: str = Field(min_length=1, description="用户名")
    password: str = Field(min_length=1, description="口令。只用于校验，不落库也不进日志")


class RegisterRequest(BaseModel):
    """自助注册。

    **没有角色字段**：注册出来的一律是学生。能自选角色等于能自选配额档，
    而配额是 `teacher` 与 `student` 唯一的实质差别。
    """

    name: str = Field(min_length=1, max_length=MAX_NAME_LENGTH, description="用户名，全库唯一")
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, description="口令。只用于算哈希，不落库也不进日志")
    invite_code: str | None = Field(
        default=None,
        description="教师给的邀请码。填对了直接进组并可以登录；不填则账号先停用，等管理员激活",
    )


class RegisterResponse(BaseModel):
    """注册的结果。

    **`is_active` 必须回传**：它决定使用者接下来该去登录还是该去等管理员，
    而这两句话说错一句就会变成一通电话。
    """

    id: str = Field(min_length=1, description="用户标识")
    name: str = Field(min_length=1, description="用户名")
    role: UserRole = Field(description="角色，注册出来的一律是学生")
    is_active: bool = Field(description="能不能直接登录。凭邀请码注册即为 true")
    group_name: str | None = Field(default=None, description="凭邀请码进的组；没填码时为空")


class MeResponse(BaseModel):
    """当前登录用户。

    **不含「所属组」**：那要多查一张表，而认身份这条路径每个请求都要走一次；
    所属组走 `/groups/mine`，页面上需要时才取。
    """

    id: str = Field(min_length=1, description="用户标识")
    name: str = Field(min_length=1, description="用户名")
    role: UserRole = Field(description="角色，前端据此决定是否显示管理入口")


class CreateUserRequest(BaseModel):
    """管理员建一个账号。**教师账号唯一的来源** —— 自助注册出来的一律是学生。"""

    name: str = Field(min_length=1, max_length=MAX_NAME_LENGTH, description="用户名，全库唯一")
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, description="初始口令。只用于算哈希，不落库也不进日志")
    role: UserRole = Field(description="角色")


class SetActiveRequest(BaseModel):
    """启用或停用一个账号。"""

    is_active: bool = Field(description="停用之后只是登不上，数据全部留在原处")


class UserResponse(BaseModel):
    """一个账号。**不含口令哈希** —— 它只在登录那一条路径上用得着。"""

    id: str = Field(min_length=1, description="用户标识")
    name: str = Field(min_length=1, description="用户名")
    role: UserRole = Field(description="角色")
    is_active: bool = Field(description="能不能登录。注册后等激活与被管理员停用都是 false")


class CreateGroupRequest(BaseModel):
    """管理员建一个课题组。"""

    name: str = Field(min_length=1, max_length=MAX_NAME_LENGTH, description="组名，全库唯一 —— 重名学生没法分辨")
    owner_id: str = Field(min_length=1, description="组主，必须是已存在的账号；它当场进这个组的名册")


class GroupResponse(BaseModel):
    """一个组，**带邀请码**。

    因此只回给组主与管理员：邀请码是准入凭证，跟着谁都看得到的列表发出去就等于没有。
    """

    id: str = Field(min_length=1, description="组标识")
    name: str = Field(min_length=1, description="组名")
    owner_id: str = Field(min_length=1, description="组主")
    invite_code: str = Field(min_length=1, description="邀请码，教师发给学生用来注册或申请入组")


class GroupSummaryResponse(BaseModel):
    """浏览列表里的一个组。**没有邀请码** —— 这一页对所有登录用户开放。"""

    id: str = Field(min_length=1, description="组标识")
    name: str = Field(min_length=1, description="组名")
    owner_name: str = Field(min_length=1, description="组主姓名")
    member_count: int = Field(ge=0, description="人数")


class MyGroupResponse(BaseModel):
    """我所属的一个组。"""

    id: str = Field(min_length=1, description="组标识")
    name: str = Field(min_length=1, description="组名")
    is_owner: bool = Field(description="我是不是这个组的组主，前端据此决定显不显示管理入口")
    invite_code: str | None = Field(
        default=None, description="邀请码。**只发给组主** —— 组员手上有码的话，招人这件事就绕开教师了"
    )


class GroupMemberResponse(BaseModel):
    """名册上的一个人。"""

    user_id: str = Field(min_length=1, description="用户标识，移出成员时用它")
    name: str = Field(min_length=1, description="用户名")
    role: UserRole = Field(description="角色")


class AddMemberRequest(BaseModel):
    """把一个已有账号加进组。

    **按用户名而不是 id**：教师手上有的是学生报上来的名字，让他先去查一个 uuid
    不现实。移出成员则相反 —— 那是从名册上点，名册里带着 id。
    """

    name: str = Field(min_length=1, max_length=MAX_NAME_LENGTH, description="要加进来的账号用户名")


class JoinRequestResponse(BaseModel):
    """一条入组申请。

    两头的名字都带着：教师的待办列表要显示「谁申请的」，学生的申请列表要显示
    「申请的是哪个组」。
    """

    id: str = Field(min_length=1, description="申请标识")
    group_id: str = Field(min_length=1, description="目标组")
    group_name: str = Field(min_length=1, description="组名")
    user_id: str = Field(min_length=1, description="申请人")
    user_name: str = Field(min_length=1, description="申请人姓名")
    status: JoinRequestStatus = Field(description="待审批 / 已批准 / 已否决")
    created_at: datetime = Field(description="申请时间")


class DecideJoinRequest(BaseModel):
    """组主对一条申请的处理。"""

    approved: bool = Field(description="批准还是否决")


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
    """上传一个文件的结果。"""

    filename: str = Field(min_length=1, description="落盘后的文件名，可能与上传时不同")
    # **不能靠 `directory + filename` 拼出来**：文件名会被收成末段，拼出来的可能不是
    # 真正落盘的那个。前端拿它去预览与下载
    path: str = Field(min_length=1, description="落盘后相对会话根的路径")
    size: int = Field(ge=0, description="字节数")


class WorkspaceEntryResponse(BaseModel):
    """工作目录里的一个条目。"""

    path: str = Field(min_length=1, description="相对会话根的路径，posix 分隔。预览与下载都用它")
    is_dir: bool = Field(description="是不是目录")
    size: int = Field(ge=0, description="字节数，目录的值没有意义")
    modified_at: datetime = Field(description="最后修改时间，UTC")


class WorkspaceTreeResponse(BaseModel):
    """会话工作目录的结构。

    给的是一份**扁平**的条目表而不是嵌套的树：路径本身已经带着层级，
    嵌套结构在 JSON 里既难分页也难增量更新，拼树是前端一行 reduce 的事。
    """

    entries: list[WorkspaceEntryResponse] = Field(description="按路径排序，父目录排在它的子项之前")
    truncated: bool = Field(description="文件太多被砍过，给的只是其中一批")


class FileContentResponse(BaseModel):
    """一个文件的一段文本内容。"""

    path: str = Field(min_length=1, description="相对会话根的路径")
    text: str = Field(description="窗口内的文本。二进制文件为空")
    total_line: int = Field(ge=0, description="读到的总行数。truncated 为真时只是开头那一截的行数")
    start_line: int = Field(ge=0, description="窗口首行，1-indexed。窗口为空时是 0")
    end_line: int = Field(ge=0, description="窗口末行，1-indexed。窗口为空时是 0")
    is_binary: bool = Field(description="不是文本。前端该改用原始字节那个端点，图片直接塞进 <img>")
    truncated: bool = Field(description="文件太长，只读了开头一截")


class RunRequest(BaseModel):
    """提交一次分析。"""

    content: str = Field(min_length=1, description="教师的问题")


class RunResponse(BaseModel):
    """run 的详情。"""

    id: str = Field(min_length=1, description="run 标识")
    thread_id: str = Field(min_length=1, description="所属会话")
    status: RunStatus = Field(description="当前状态")


class UserUsageResponse(BaseModel):
    """一个用户在窗口内的用量。**只有数字与身份，没有会话内容**。"""

    user_id: str = Field(min_length=1, description="用户标识")
    name: str = Field(min_length=1, description="用户名，看板上「谁」这一列")
    role: UserRole = Field(description="角色。配额按角色分档，账因此也按角色看")
    runs: int = Field(ge=0, description="跑过几次分析")
    cache_read: int = Field(ge=0, description="命中 prompt cache 的 input token，几乎不要钱")
    uncached: int = Field(ge=0, description="未命中的 input token，配额与成本都按它算")
    output: int = Field(ge=0, description="output token")


class DayUsageResponse(BaseModel):
    """某一天的用量，跨全部用户。"""

    day: date = Field(description="日期，UTC")
    runs: int = Field(ge=0, description="当天跑过几次分析")
    cache_read: int = Field(ge=0, description="命中 prompt cache 的 input token")
    uncached: int = Field(ge=0, description="未命中的 input token")
    output: int = Field(ge=0, description="output token")


class UsageResponse(BaseModel):
    """成本看板的数据。

    **窗口一并回传**：看板上那个数是「哪一段时间的」，不写出来就没法核对。
    """

    since: datetime = Field(description="窗口起点（含）")
    until: datetime = Field(description="窗口终点（不含）")
    days: int = Field(gt=0, description="窗口长度，天")
    users: list[UserUsageResponse] = Field(description="按未命中 token 从多到少排")
    daily: list[DayUsageResponse] = Field(description="按天从早到晚排。没有 run 的那天不占一行")
