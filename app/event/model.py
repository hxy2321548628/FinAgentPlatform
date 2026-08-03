"""平台事件的信封与类型枚举。

这是前后端唯一共用的契约：前端的校验 schema 直接照这里写。本模块只描述事件长什么样，
不关心它从哪来 —— 把 DeepAgents 的流翻译过来的是同包的 mapper。

信封里**没有 `id`**：事件 id 由事件日志在追加时分配（形状对齐 Redis Stream ID），
断线重连的 `Last-Event-ID` 认的就是那个号。映射层自己发号会与日志的号撞车。
"""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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


class EventEnvelope(BaseModel):
    """所有事件共用的信封，`type` 之外的字段与事件种类无关。

    事件进日志后会被多个 SSE 连接同时读取，因此冻结 —— 谁都不该改已经发生的事。
    """

    model_config = ConfigDict(frozen=True)

    type: EventType = Field(description="事件类型，前端据此选择渲染分支")
    ts: int = Field(description="服务端毫秒时间戳")
    run_id: str = Field(min_length=1, description="所属 run，便于前端在多 run 并存时路由")
    path: tuple[str, ...] = Field(description="子 agent 归属，空元组为主 agent")


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


type Event = TokenEvent | ReasoningEvent | ToolCallEvent | ToolResultEvent
