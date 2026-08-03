"""DeepAgents 的流到平台事件的映射，也就是防腐层。

`astream(stream_mode=["updates","messages","custom"], subgraphs=True)` 吐出
`(ns, mode, payload)` 三元组，本模块把它翻译成平台自己的事件词汇 ——
前端因此不必知道 LangGraph 的节点命名，框架升级也只需要改这里。

**不认识的形状记警告后跳过，不抛异常。** 一次分析要跑几十分钟，
不该因为 DeepAgents 多吐了一种没见过的 chunk 就整个失败。
"""

import logging
import time
from dataclasses import dataclass

from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage

from event.model import (
    Event,
    ReasoningData,
    ReasoningEvent,
    TokenData,
    TokenEvent,
    ToolCallData,
    ToolCallEvent,
    ToolResultData,
    ToolResultEvent,
)

logger = logging.getLogger(__name__)

# astream 在 stream_mode 传 list 且 subgraphs=True 时吐出的三元组。
# payload 的形状随 mode 而变，因此只能标到 object，由本模块逐个收窄。
type StreamChunk = tuple[tuple[str, ...], str, object]

# updates 模式下承载模型输出与工具结果的两个节点名。
# 工具不按名字分节点 —— 8 个内置工具共用一个 tools 节点。
MODEL_NODE = "model"
TOOLS_NODE = "tools"

REASONING_KEY = "reasoning_content"


@dataclass(frozen=True)
class _Stamp:
    """一个 chunk 映射出的所有事件共享的信封字段。"""

    ts: int
    run_id: str
    path: tuple[str, ...]


def map_chunk(ns: tuple[str, ...], mode: str, payload: object, *, run_id: str) -> list[Event]:
    """把一个 DeepAgents chunk 映射成零个或多个平台事件。

    Args:
        ns: LangGraph 的节点路径，在子图内执行时非空。
        mode: astream 的流模式。
        payload: 该模式的载荷，形状随 mode 而变。
        run_id: 事件所属的 run。

    Returns:
        按发生顺序排列的事件；该 chunk 不对应任何平台事件时为空列表。
    """
    stamp = _Stamp(ts=_now_ms(), run_id=run_id, path=_map_path(ns))
    match mode:
        case "messages":
            return _map_streamed(payload, stamp)
        case "updates":
            return _map_update(payload, stamp)
        case "custom":
            # 沙箱工具用 get_stream_writer() 往这个通道写 sandbox.* 事件。
            # 排队逻辑尚未实现，载荷契约未定，先不映射。
            return []
        case _:
            logger.warning("未知的流模式，已跳过：mode=%s", mode)
            return []


def _map_streamed(payload: object, stamp: _Stamp) -> list[Event]:
    """映射 messages 模式：模型逐字流出的增量。"""
    if not isinstance(payload, tuple) or not payload:
        logger.warning("messages 载荷不是 (message, metadata) 二元组，已跳过")
        return []

    message = payload[0]
    if isinstance(message, ToolMessage):
        # 同一条 ToolMessage 也会从 updates 的 tools 节点流出，在那里映射成 tool_result。
        # 两处都映射，前端会收到重复的工具结果。
        return []
    if not isinstance(message, AIMessageChunk):
        logger.warning("messages 里出现未知消息类型，已跳过：%s", type(message).__name__)
        return []

    events: list[Event] = []
    reasoning = message.additional_kwargs.get(REASONING_KEY)
    if isinstance(reasoning, str) and reasoning:
        events.append(
            ReasoningEvent(ts=stamp.ts, run_id=stamp.run_id, path=stamp.path, data=ReasoningData(text=reasoning))
        )
    text = str(message.text)
    if text:
        events.append(TokenEvent(ts=stamp.ts, run_id=stamp.run_id, path=stamp.path, data=TokenData(text=text)))
    # message.tool_call_chunks 是工具参数的逐字流，只有要做参数级流式渲染时才用得上。
    # 完整调用统一取自 updates 的 model 节点，这里不映射以免同一次调用发两遍。
    return events


def _map_update(payload: object, stamp: _Stamp) -> list[Event]:
    """映射 updates 模式：节点执行完毕后的状态更新。"""
    if not isinstance(payload, dict):
        logger.warning("updates 载荷不是节点字典，已跳过")
        return []

    events: list[Event] = []
    for node, update in payload.items():
        # 中间件节点（如 PatchToolCallsMiddleware.before_agent）不改状态，载荷为 None
        if update is None:
            continue
        events.extend(_map_node(str(node), update, stamp))
    return events


def _map_node(node: str, update: object, stamp: _Stamp) -> list[Event]:
    if not isinstance(update, dict) or "messages" not in update:
        logger.warning("updates 节点的载荷里没有 messages，已跳过：node=%s", node)
        return []

    message = update["messages"]
    if not isinstance(message, list):
        logger.warning("updates 节点的 messages 不是列表，已跳过：node=%s", node)
        return []

    if node == MODEL_NODE:
        return [event for one in message for event in _map_tool_call(one, stamp)]
    if node == TOOLS_NODE:
        return [event for one in message for event in _map_tool_result(one, stamp)]

    logger.warning("未知的 updates 节点，已跳过：node=%s", node)
    return []


def _map_tool_call(message: object, stamp: _Stamp) -> list[Event]:
    """映射 model 节点：取 AIMessage 决定调用的工具。

    这条 AIMessage 的正文此前已由 messages 模式逐字流过，
    这里只取 tool_calls，否则整段答复会重复一遍。
    """
    if not isinstance(message, AIMessage):
        logger.warning("model 节点里出现非 AIMessage，已跳过：%s", type(message).__name__)
        return []

    # ToolCall 的 id 在类型上可空，但 OpenAI 兼容接口必然给值 —— 缺了也只是配不上结果，
    # 不值得为此丢掉整条事件。
    return [
        ToolCallEvent(
            ts=stamp.ts,
            run_id=stamp.run_id,
            path=stamp.path,
            data=ToolCallData(id=call["id"] or "", name=call["name"], args=dict(call["args"])),
        )
        for call in message.tool_calls
    ]


def _map_tool_result(message: object, stamp: _Stamp) -> list[Event]:
    """映射 tools 节点：取工具执行完毕的返回。"""
    if not isinstance(message, ToolMessage):
        logger.warning("tools 节点里出现非 ToolMessage，已跳过：%s", type(message).__name__)
        return []

    return [
        ToolResultEvent(
            ts=stamp.ts,
            run_id=stamp.run_id,
            path=stamp.path,
            data=ToolResultData(
                tool_call_id=message.tool_call_id,
                name=message.name or "",
                content=str(message.text),
                status=message.status,
            ),
        )
    ]


def _map_path(ns: tuple[str, ...]) -> tuple[str, ...]:
    """把 LangGraph 的节点路径收成可读的名字。

    路径的每一段形如 `research:9d1f0a2b`，冒号后是随机 task id ——
    透出去就是让前端耦合 LangGraph 的内部命名。

    本期不开子 agent，实测 ns 全程为空，这条剥离逻辑没有真实子图样本验证过。
    """
    return tuple(segment.split(":", 1)[0] for segment in ns)


def _now_ms() -> int:
    return time.time_ns() // 1_000_000
