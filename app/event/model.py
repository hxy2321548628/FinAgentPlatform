"""平台事件的信封与类型枚举。

这是前后端唯一共用的契约：前端的校验 schema 直接照这里写。本模块只描述事件长什么样，
不关心它从哪来 —— 把 DeepAgents 的流翻译过来的是同包的 mapper。

信封里**没有 `id`**：事件 id 由事件日志在追加时分配（形状对齐 Redis Stream ID），
断线重连的 `Last-Event-ID` 认的就是那个号。映射层自己发号会与日志的号撞车。
"""

import time
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Discriminator, Field, TypeAdapter


def now_ms() -> int:
    """返回信封 `ts` 用的服务端毫秒时间戳。"""
    return time.time_ns() // 1_000_000


class EventType(StrEnum):
    """事件类型的完整清单。

    平台层由平台自己产生，DeepAgents 不参与；Agent 层映射自 DeepAgents 的流。
    枚举列全清单是为了让前端有一份完整的类型表，但不是每种都已有对应的事件模型 ——
    模型随各步骤落地时才添加。
    """

    RUN_STARTED = "run.started"
    RUN_FINISHED = "run.finished"
    RUN_FAILED = "run.failed"
    RUN_CANCELLED = "run.cancelled"
    SANDBOX_QUEUED = "sandbox.queued"
    SANDBOX_READY = "sandbox.ready"
    ERROR = "error"

    TOKEN = "token"
    REASONING = "reasoning"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    TODO_UPDATED = "todo.updated"
    SUBAGENT_STARTED = "subagent.started"
    SUBAGENT_FINISHED = "subagent.finished"
    INTERRUPT = "interrupt"


class RunStatus(StrEnum):
    """run 的生命周期状态。

    `waiting_approval` 要等 HITL 审批落地才会出现。
    """

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunErrorCode(StrEnum):
    """run 失败的原因，前端据此决定提示语。

    与 HTTP 错误的 code 是两套：那套描述「这个请求为什么被拒」，
    这套描述「这个已经在跑的 run 为什么没跑完」。
    """

    SANDBOX_QUEUE_TIMEOUT = "SANDBOX_QUEUE_TIMEOUT"
    INTERNAL = "INTERNAL"


class EventEnvelope(BaseModel):
    """所有事件共用的信封，`type` 之外的字段与事件种类无关。

    事件进日志后会被多个 SSE 连接同时读取，因此冻结 —— 谁都不该改已经发生的事。
    """

    model_config = ConfigDict(frozen=True)

    type: EventType = Field(description="事件类型，前端据此选择渲染分支")
    ts: int = Field(description="服务端毫秒时间戳")
    run_id: str = Field(min_length=1, description="所属 run，便于前端在多 run 并存时路由")
    path: tuple[str, ...] = Field(description="子 agent 归属，空元组为主 agent")


class RunStartedData(BaseModel):
    """`run.started` 事件的载荷。"""

    thread_id: str = Field(min_length=1, description="run 所属的会话")


class TokenUsage(BaseModel):
    """一次 run 的 token 消耗，按计费单价不同的三部分分开记。

    **刻意不给总数**：命中 prompt cache 的 input 单价远低于未命中部分，加总之后的数字
    既不对应成本、也不能拿来算配额 —— P0 实测 62% 的 input 是命中，按总量记会高估约
    1.6 倍，且会话越长高估越多，方向性地惩罚长会话。
    """

    input_cache_read: int = Field(default=0, ge=0, description="命中 prompt cache 的 input token")
    input_uncached: int = Field(default=0, ge=0, description="未命中 cache 的 input token，配额按这部分加权计算")
    output: int = Field(default=0, ge=0, description="output token，含 reasoning 部分")

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        """把两次模型调用的用量相加。一次 run 有十几次调用，总量是逐次累加出来的。"""
        return TokenUsage(
            input_cache_read=self.input_cache_read + other.input_cache_read,
            input_uncached=self.input_uncached + other.input_uncached,
            output=self.output + other.output,
        )


class RunFinishedData(BaseModel):
    """`run.finished` 事件的载荷。"""

    status: Literal[RunStatus.SUCCEEDED] = Field(
        default=RunStatus.SUCCEEDED,
        description="正常完成才发这个事件，失败走 run.failed",
    )
    tokens: TokenUsage = Field(
        default_factory=TokenUsage,
        description="本次 run 的 token 消耗，按 cache 命中拆分",
    )
    artifacts: list[str] = Field(
        default_factory=list,
        description="本次 run 产出的产物标识，拼上产物端点即可下载",
    )


class RunFailedData(BaseModel):
    """`run.failed` 事件的载荷。"""

    code: RunErrorCode = Field(description="失败原因，稳定的机器可读枚举")
    message: str = Field(min_length=1, description="中文说明，前端可直接展示")
    retryable: bool = Field(description="重试是否有意义，前端据此决定要不要显示重试按钮")


class RunCancelledData(BaseModel):
    """`run.cancelled` 事件的载荷。

    **带上取消那一刻的用量**：教师点「停止」多半是因为觉得跑偏了，
    而「这次白花了多少」是他下一个要问的问题。
    """

    tokens: TokenUsage = Field(
        default_factory=TokenUsage,
        description="取消之前已经消耗的 token，按 cache 命中拆分",
    )


class SandboxQueuedData(BaseModel):
    """`sandbox.queued` 事件的载荷。"""

    position: int = Field(ge=1, description="当前排位，1 表示下一个就轮到自己")


class ErrorData(BaseModel):
    """`error` 事件的载荷。

    与 `run.failed` 的区别是**是否终止 run**：这个只是过程中的告警。
    """

    code: RunErrorCode = Field(description="错误分类")
    message: str = Field(min_length=1, description="中文说明")


class TokenData(BaseModel):
    """`token` 事件的载荷。"""

    text: str = Field(min_length=1, description="正式答复的增量文本")


class ReasoningData(BaseModel):
    """`reasoning` 事件的载荷。"""

    text: str = Field(min_length=1, description="思考过程的增量文本")


class ToolCallData(BaseModel):
    """`tool_call` 事件的载荷。"""

    id: str = Field(description="工具调用标识，与 tool_result 的 tool_call_id 配对")
    name: str = Field(min_length=1, description="被调用的工具名")
    args: dict[str, object] = Field(description="调用参数，形状由工具自己定义")


class ToolResultData(BaseModel):
    """`tool_result` 事件的载荷。"""

    tool_call_id: str = Field(description="对应的 tool_call 标识")
    name: str = Field(description="产生该结果的工具名")
    content: str = Field(description="工具返回的文本，出错时是错误描述")
    status: Literal["success", "error"] = Field(description="工具自身的成败，与 run 的成败无关")


class SandboxReadyData(BaseModel):
    """`sandbox.ready` 事件的载荷。

    契约上是空对象。留成模型而不是省掉 `data` 字段，是为了让前端拿到的信封形状一致，
    且将来要带上沙箱标识时不必改事件的类型。
    """


class RunStartedEvent(EventEnvelope):
    """worker 领取任务，开始执行。"""

    type: Literal[EventType.RUN_STARTED] = EventType.RUN_STARTED
    data: RunStartedData


class RunFinishedEvent(EventEnvelope):
    """run 正常完成，终态。"""

    type: Literal[EventType.RUN_FINISHED] = EventType.RUN_FINISHED
    data: RunFinishedData


class RunFailedEvent(EventEnvelope):
    """run 异常终止，终态。"""

    type: Literal[EventType.RUN_FAILED] = EventType.RUN_FAILED
    data: RunFailedData


class RunCancelledEvent(EventEnvelope):
    """教师主动取消，终态。

    与 `run.failed` 分开是因为它不是故障：前端不该显示「重试」按钮，也不该报错。
    """

    type: Literal[EventType.RUN_CANCELLED] = EventType.RUN_CANCELLED
    data: RunCancelledData


class SandboxQueuedEvent(EventEnvelope):
    """沙箱已满，正在排队。排位每次变化都会推一条。"""

    type: Literal[EventType.SANDBOX_QUEUED] = EventType.SANDBOX_QUEUED
    data: SandboxQueuedData


class SandboxReadyEvent(EventEnvelope):
    """拿到沙箱，排队结束。"""

    type: Literal[EventType.SANDBOX_READY] = EventType.SANDBOX_READY
    data: SandboxReadyData


class ErrorEvent(EventEnvelope):
    """不终止 run 的非致命错误。"""

    type: Literal[EventType.ERROR] = EventType.ERROR
    data: ErrorData


class TokenEvent(EventEnvelope):
    """模型正式答复的增量。"""

    type: Literal[EventType.TOKEN] = EventType.TOKEN
    data: TokenData


class ReasoningEvent(EventEnvelope):
    """模型思考过程的增量。

    与 `token` 分开是因为它们在模型侧就是两个字段、交替流出，
    合并会让前端把思考和结论渲染在一起。
    """

    type: Literal[EventType.REASONING] = EventType.REASONING
    data: ReasoningData


class ToolCallEvent(EventEnvelope):
    """模型决定调用某个工具。"""

    type: Literal[EventType.TOOL_CALL] = EventType.TOOL_CALL
    data: ToolCallData


class ToolResultEvent(EventEnvelope):
    """工具执行完毕的返回。"""

    type: Literal[EventType.TOOL_RESULT] = EventType.TOOL_RESULT
    data: ToolResultData


type Event = (
    RunStartedEvent
    | RunFinishedEvent
    | RunFailedEvent
    | RunCancelledEvent
    | SandboxQueuedEvent
    | SandboxReadyEvent
    | ErrorEvent
    | TokenEvent
    | ReasoningEvent
    | ToolCallEvent
    | ToolResultEvent
)

# 出现即代表 run 已经结束，事件流可以收尾。SSE 端点靠它决定何时关闭连接。
TERMINAL_EVENT_TYPE = frozenset({EventType.RUN_FINISHED, EventType.RUN_FAILED, EventType.RUN_CANCELLED})

# 事件从 Redis Stream 读回来时要还原成具体的事件类型。按 `type` 判别而不是逐个试 ——
# 逐个试会让载荷形状相近的两种事件互相冒认，而那种错不报错，只是渲染成了别的东西。
EVENT_ADAPTER: TypeAdapter[Event] = TypeAdapter(Annotated[Event, Discriminator("type")])
