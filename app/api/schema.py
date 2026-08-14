"""对外接口的请求与响应模型。

只放 HTTP 层自己的形状。**事件不在这里** —— 那是前后端共用的契约，
定义在事件包里，SSE 直接把它序列化出去。
"""

from datetime import datetime

from pydantic import BaseModel, Field

from agent.config import MAX_SYSTEM_PROMPT_LENGTH, AgentConfigRequest, SkillReference
from event.model import RunErrorCode, RunStatus
from group.model import JoinRequestStatus
from preset.model import ResourceKind, ReviewStatus, VersionStatus, Visibility
from preset.repository import AgentSource
from preset.skill import SkillSource
from run.decision import Decision
from user.model import UserRole

# 自助注册的口令下限。**登录不设这个下限**：那会把已有的短口令账号一次性锁在门外，
# 而它们的强度不会因为登录端点多一条校验而变好
MIN_PASSWORD_LENGTH = 8

# 用户名与组名的长度上限。库里这两列是不限长的 varchar，挡住超长输入的只有这里
MAX_NAME_LENGTH = 32

# 教师手填标题的长度上限。**比自动生成的那个上限宽**（那个是 20 字的硬截断）——
# 模型要写得下侧边栏一行，人手起的名字则是他自己的事，只要不能拿来灌库
MAX_THREAD_TITLE_LENGTH = 64

# 智能体的名称、说明、学科的长度上限。名称要写得下广场卡片一行，
# 说明是卡片上那两行摘要，学科是个标签
MAX_AGENT_NAME_LENGTH = 32
MAX_AGENT_DESCRIPTION_LENGTH = 200
MAX_AGENT_SUBJECT_LENGTH = 32

# 拒绝理由的长度上限。**下限是 1 且后端也校验** —— 只靠前端拦的话，
# 任何一次直接打接口都能留下一条没有理由的拒绝，而作者看到的是「被拒了，没说为什么」
MAX_REVIEW_REASON_LENGTH = 500

# 一个作者一次能共享给几个组。学院里一个老师带的组是个位数，
# 这道闸拦的是「把一个 uuid 列表灌到上万条」
MAX_SHARED_GROUP = 20


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
    """一个会话。"""

    id: str = Field(min_length=1, description="会话标识，后续所有操作都带它")
    title: str = Field(
        description="会话标题。首次提问后由一次轻量模型调用填上，**在那之前是空的** —— 前端此时回落到时间显示"
    )
    created_at: datetime = Field(description="建立时间，UTC")
    # 列表按它倒序。提交分析与改标题都会把它推到此刻
    updated_at: datetime = Field(description="最后活动时间，UTC")


class ThreadDetailResponse(ThreadResponse):
    """会话详情，比列表里那份多一份 agent 配置。

    配置整块读写，不按字段查询 —— 后续方向（自定义提示词、skill、MCP）会持续往里加东西。
    """

    agent_config: dict[str, object] = Field(description="这个会话的 agent 配置")


class ThreadPageResponse(BaseModel):
    """一页会话。"""

    items: list[ThreadResponse] = Field(description="按最后活动时间从近到远排")
    next_cursor: str | None = Field(
        description="取下一页要原样带回来的游标。**为空表示到底了** —— 前端据此停止「加载更多」"
    )


class UpdateThreadRequest(BaseModel):
    """改一个会话。

    **两个字段各自可选**：只传标题时配置原样留着 —— 一次改名把 agent 配置清空，
    是那种改完当时没事、下次跑分析才发现的故障。
    """

    title: str | None = Field(default=None, max_length=MAX_THREAD_TITLE_LENGTH, description="新标题，不传则不动")
    agent_config: AgentConfigRequest | None = Field(
        default=None, description="新配置，**整块替换**而不是合并，不传则不动"
    )


class RunHistoryResponse(BaseModel):
    """会话历史里的一轮问答。

    **过程不在这里**：那是 `GET /runs/{id}/events` 逐个重放的事件，一轮几百条，
    塞进列表会让打开会话变成一次几 MB 的下载。这里给的是「问了什么、结局如何」。
    """

    id: str = Field(min_length=1, description="run 标识，拿它去订阅或重放事件")
    status: RunStatus = Field(description="当前状态")
    content: str | None = Field(description="教师的问题。**本版之前的 run 为空** —— 那批提问没有落过库，不是待补的空缺")
    error_code: RunErrorCode | None = Field(default=None, description="失败原因，稳定的机器可读枚举")
    error_message: str | None = Field(default=None, description="失败说明，中文，可直接展示")
    started_at: datetime = Field(description="提交时间，UTC")
    ended_at: datetime | None = Field(default=None, description="结束时间，UTC。还在跑的为空")
    agent_config: dict[str, object] = Field(description="这一轮实际生效的 agent 配置快照")


class RunPageResponse(BaseModel):
    """一页会话历史。"""

    items: list[RunHistoryResponse] = Field(description="按提交时间**从近到远**排，前端倒过来渲染")
    next_cursor: str | None = Field(description="取下一页（更早那些）要原样带回来的游标；为空表示翻到头了")


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
    agent_config: AgentConfigRequest | None = Field(
        default=None,
        description="这一轮的配置覆盖；不传则继承会话默认，空对象表示改回平台默认",
    )


class RunResponse(BaseModel):
    """run 的详情。"""

    id: str = Field(min_length=1, description="run 标识")
    thread_id: str = Field(min_length=1, description="所属会话")
    status: RunStatus = Field(description="当前状态")
    agent_config: dict[str, object] = Field(description="这一次 run 实际生效的配置快照")


class CreateAgentRequest(BaseModel):
    """建一个智能体。**连带它的 v1 草稿** —— 没有「只有身份没有内容」的中间态。"""

    name: str = Field(min_length=1, max_length=MAX_AGENT_NAME_LENGTH, description="名称，**同一作者名下唯一**")
    description: str = Field(default="", max_length=MAX_AGENT_DESCRIPTION_LENGTH, description="一句话说明")
    subject: str = Field(default="", max_length=MAX_AGENT_SUBJECT_LENGTH, description="学科")
    system_prompt: str = Field(
        min_length=1,
        max_length=MAX_SYSTEM_PROMPT_LENGTH,
        description="提示词",
    )
    skills: list[str] | None = Field(default=None, description="这个草稿自带的 Skill 标识")


class UpdateAgentRequest(BaseModel):
    """改元信息。**不产生新版本** —— 改名与改提示词是两件事。"""

    name: str = Field(min_length=1, max_length=MAX_AGENT_NAME_LENGTH, description="新名称")
    description: str = Field(default="", max_length=MAX_AGENT_DESCRIPTION_LENGTH, description="新说明")
    subject: str = Field(default="", max_length=MAX_AGENT_SUBJECT_LENGTH, description="新学科")


class UpdateDraftRequest(BaseModel):
    """改草稿的内容。没有草稿时**追加下一个版本号的新草稿**。"""

    system_prompt: str = Field(min_length=1, max_length=MAX_SYSTEM_PROMPT_LENGTH, description="新的提示词")
    skills: list[str] | None = Field(default=None, description="这个草稿自带的 Skill 标识；整块替换")


class SetSharingRequest(BaseModel):
    """设可见性与共享给哪些组。

    **平台目录不在这里** —— 那一档要 reviewer 点头，不是作者能拨的开关。
    """

    visibility: Visibility = Field(description="私有还是组内")
    group_ids: list[str] = Field(
        default_factory=list,
        max_length=MAX_SHARED_GROUP,
        description="共享给哪些组，**整块替换**。只能填自己在里面的组",
    )


class SubmitReviewRequest(BaseModel):
    """把当前最新的已发布版本提交给审核。"""

    responsibility_confirmed: bool = Field(description="责任确认。**没勾一律 422**，后端也校验 —— 出了事要拿这一列说话")


class DecideReviewRequest(BaseModel):
    """reviewer 的决策。"""

    approved: bool = Field(description="通过还是拒绝")
    reason: str | None = Field(
        default=None,
        max_length=MAX_REVIEW_REASON_LENGTH,
        description="拒绝理由。**拒绝时必填**，通过时忽略 —— 通过不需要解释，拒绝必须给作者一句能照着改的话",
    )


class AgentVersionResponse(BaseModel):
    """作者视角的一个版本，连同它的审核状态。"""

    id: str = Field(min_length=1, description="版本行标识，提审时用它")
    version: int = Field(ge=1, description="版本号")
    status: VersionStatus = Field(description="作者定没定稿")
    system_prompt: str = Field(description="这一版的提示词")
    skill_refs: list[SkillReference] | None = Field(default=None, description="这一版冻结的 Skill 引用")
    created_at: datetime = Field(description="建立时间，UTC")
    released_at: datetime | None = Field(default=None, description="定稿时间，UTC。草稿为空")
    review_id: str | None = Field(default=None, description="最近一条审核记录；从没提审过则为空")
    review_status: ReviewStatus | None = Field(default=None, description="最近一条审核的状态")
    review_reason: str | None = Field(default=None, description="被拒时的理由，一字不差")


class MyAgentResponse(BaseModel):
    """作者视角的一个智能体。

    **五个状态映到三个页签**（草稿 / 待审 / 已发布），映射由前端做 —— 后端给的是事实。
    """

    id: str = Field(min_length=1, description="智能体标识")
    name: str = Field(min_length=1, description="名称")
    description: str = Field(description="一句话说明")
    subject: str = Field(description="学科")
    visibility: Visibility = Field(description="私有还是组内")
    call_count: int = Field(ge=0, description="被引用过几次。**不去重、不实时**")
    is_deleted: bool = Field(description="删过了没有。删掉的只有作者自己看得到")
    in_catalog: bool = Field(description="有没有一个版本在平台目录里")
    group_ids: list[str] = Field(description="共享给了哪些组")
    versions: list[AgentVersionResponse] = Field(description="全部版本，按版本号从小到大")
    created_at: datetime = Field(description="建立时间，UTC")
    updated_at: datetime = Field(description="最后改动时间，UTC")


class AgentListingResponse(BaseModel):
    """广场与「我能引用的」共用的一行。

    **提示词全文在里面**：看不到内容就判断不了一个 agent 值不值得用，
    而「共享出去的东西别人看得见内容」本来就是共享的含义。
    """

    id: str = Field(min_length=1, description="智能体标识，引用时把它填进 agent_config")
    owner_id: str = Field(min_length=1, description="作者标识")
    owner_name: str = Field(min_length=1, description="作者姓名 —— 广场上重名靠它区分")
    name: str = Field(min_length=1, description="名称")
    description: str = Field(description="一句话说明")
    subject: str = Field(description="学科")
    visibility: Visibility = Field(description="作者拨的那一档")
    call_count: int = Field(ge=0, description="被引用过几次")
    version: int = Field(ge=1, description="**这一档下展示的是哪一版**。广场看最新过审版，组内看最新已发布版")
    system_prompt: str = Field(description="那一版的提示词全文")
    skill_refs: list[SkillReference] | None = Field(default=None, description="这一版自带的 Skill")
    source: AgentSource = Field(description="凭哪一条进到这个列表：我自己的 / 组内共享 / 平台目录")
    updated_at: datetime = Field(description="最后改动时间，UTC")


class UpdateSkillRequest(BaseModel):
    """Skill 的身份元信息；name 由首版 frontmatter 冻结。"""

    subject: str = Field(default="", max_length=MAX_AGENT_SUBJECT_LENGTH, description="学科")


class SkillVersionResponse(BaseModel):
    """一个 Skill 版本及它最近一次审核状态。"""

    id: str = Field(min_length=1, description="版本行标识")
    version: int = Field(ge=1, description="版本号")
    status: VersionStatus = Field(description="草稿或已发布")
    description: str = Field(description="该版 frontmatter 的 description")
    file_count: int = Field(ge=1, description="文件数量")
    total_bytes: int = Field(ge=0, description="文件总字节数")
    created_at: datetime = Field(description="上传时间，UTC")
    released_at: datetime | None = Field(default=None, description="发布时间，UTC")
    review_id: str | None = Field(default=None, description="最近一次审核标识")
    review_status: ReviewStatus | None = Field(default=None, description="最近一次审核状态")
    review_reason: str | None = Field(default=None, description="最近一次拒绝理由")


class MySkillResponse(BaseModel):
    """作者视角的一条 Skill。"""

    id: str = Field(min_length=1)
    owner_name: str = Field(min_length=1)
    name: str = Field(min_length=1, description="首版 frontmatter 冻结的 name")
    subject: str
    visibility: Visibility
    call_count: int = Field(ge=0)
    is_deleted: bool
    in_catalog: bool
    group_ids: list[str]
    versions: list[SkillVersionResponse]
    created_at: datetime
    updated_at: datetime


class SkillListingResponse(BaseModel):
    """Skill 广场或可用列表的一行。"""

    id: str = Field(min_length=1)
    owner_id: str = Field(min_length=1)
    owner_name: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str
    subject: str
    visibility: Visibility
    call_count: int = Field(ge=0)
    version: int = Field(ge=1)
    file_count: int = Field(ge=1)
    total_bytes: int = Field(ge=0)
    source: SkillSource
    updated_at: datetime


class ReviewResponse(BaseModel):
    """审核队列里的一条，带 reviewer 判断需要的全部信息。"""

    id: str = Field(min_length=1, description="审核标识，决策时用它")
    target_kind: ResourceKind = Field(description="审的是 Agent 还是 Skill")
    target_id: str = Field(min_length=1, description="被审的版本行标识")
    status: ReviewStatus = Field(description="待审 / 通过 / 拒绝")
    responsibility_confirmed: bool = Field(description="作者勾没勾责任确认")
    reason: str | None = Field(default=None, description="拒绝理由")
    created_at: datetime = Field(description="提审时间，UTC")
    decided_at: datetime | None = Field(default=None, description="决策时间，UTC。待审为空")
    owner_name: str = Field(min_length=1, description="作者姓名")
    description: str = Field(description="被审版本的说明")
    subject: str = Field(description="学科")
    version: int = Field(ge=1, description="被审的是第几版")
    agent_id: str | None = Field(default=None, description="Agent 标识；Skill 审核时为空")
    agent_name: str | None = Field(default=None, description="Agent 名称；Skill 审核时为空")
    system_prompt: str | None = Field(default=None, description="Agent 提示词；Skill 审核时为空")
    skill_id: str | None = Field(default=None, description="Skill 标识；Agent 审核时为空")
    skill_name: str | None = Field(default=None, description="Skill 名称；Agent 审核时为空")
    file_count: int | None = Field(default=None, ge=1, description="Skill 文件数")
    total_bytes: int | None = Field(default=None, ge=0, description="Skill 文件总字节数")
