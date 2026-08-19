"""DeepAgents 的流到平台事件的映射，也就是防腐层。

`astream(stream_mode=["updates","messages","custom"], subgraphs=True)` 吐出
`(ns, mode, payload)` 三元组，本模块把它翻译成平台自己的事件词汇 ——
前端因此不必知道 LangGraph 的节点命名，框架升级也只需要改这里。

**不认识的形状记警告后跳过，不抛异常。** 一次分析要跑几十分钟，
不该因为 DeepAgents 多吐了一种没见过的 chunk 就整个失败。
"""

import logging
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage

from app.agent.tail import BLOCK_HEADER
from app.event.model import (
    CompactionData,
    CompactionEvent,
    Event,
    ReasoningData,
    ReasoningEvent,
    TodoItem,
    TodoUpdatedData,
    TodoUpdatedEvent,
    TokenData,
    TokenEvent,
    ToolCallData,
    ToolCallEvent,
    ToolResultData,
    ToolResultEvent,
    now_ms,
)

logger = logging.getLogger(__name__)

# astream 在 stream_mode 传 list 且 subgraphs=True 时吐出的三元组。
# payload 的形状随 mode 而变，因此只能标到 object，由本模块逐个收窄。
type StreamChunk = tuple[tuple[str, ...], str, object]

# updates 模式下承载模型输出与工具结果的两个节点名。
# 工具不按名字分节点 —— 8 个内置工具共用一个 tools 节点。
MODEL_NODE = "model"
TOOLS_NODE = "tools"
TASK_TOOL = "task"
SUBAGENT_TYPE_ARG = "subagent_type"

REASONING_KEY = "reasoning_content"

# 压缩中间件把「这一轮压了一次」写在这个私有 state 字段里。**名字由 deepagents 定**，
# 平台只是读它 —— 它换名字的话这里会静默失灵，因此 P13② 那条判据要真跑一次压缩
SUMMARIZATION_KEY = "_summarization_event"

# 任务清单中间件把整张清单写在这个 state 字段里。**名字由上游定**，与压缩痕迹同型：
# 键在就是「这一轮改过清单」，不在就不出事件
TODO_KEY = "todos"
TODO_STATUS = frozenset({"pending", "in_progress", "completed"})


@dataclass(frozen=True)
class _Stamp:
    """一个 chunk 映射出的所有事件共享的信封字段。"""

    ts: int
    run_id: str
    path: tuple[str, ...]


class EventMapper:
    """把一个 run 的 DeepAgents chunk 映射成平台事件。

    子图 namespace 只有 ``tools:<uuid>``，不带子智能体名。父图的 ``task``
    调用先到，因此按调用顺序暂存名字，在第一次看见 uuid 时建立稳定映射。
    每个 run 必须持有自己的实例，避免并发分析互相污染。
    """

    def __init__(
        self,
        run_id: str,
        *,
        known_tool_paths: Mapping[str, tuple[str, ...]] | None = None,
    ) -> None:
        self._run_id = run_id
        self._pending_subagents: deque[str] = deque()
        self._subagent_by_uuid: dict[str, str] = {}
        self._seen_task_calls: set[str] = set()
        self._known_tool_paths = dict(known_tool_paths or {})

    def map_chunk(self, ns: tuple[str, ...], mode: str, payload: object) -> list[Event]:
        """把一个 DeepAgents chunk 映射成零个或多个平台事件。

        Args:
            ns: LangGraph 的节点路径，在子图内执行时非空。
            mode: astream 的流模式。
            payload: 该模式的载荷，形状随 mode 而变。

        Returns:
            按发生顺序排列的事件；该 chunk 不对应任何平台事件时为空列表。
        """
        self._remember_subagents(ns, mode, payload)
        stamp = _Stamp(ts=now_ms(), run_id=self._run_id, path=self._map_path(ns))
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

    def _remember_subagents(self, ns: tuple[str, ...], mode: str, payload: object) -> None:
        """记住首跑的 task 名称，或从历史工具调用恢复续跑 namespace。"""
        if ns:
            self._remember_resumed_subagent(ns, mode, payload)
            return
        if mode != "updates" or not isinstance(payload, dict):
            return
        update = payload.get(MODEL_NODE)
        if not isinstance(update, dict):
            return
        messages = update.get("messages")
        if not isinstance(messages, list):
            return
        for message in messages:
            if not isinstance(message, AIMessage):
                continue
            for call in message.tool_calls:
                call_id = call["id"] or ""
                name = call["args"].get(SUBAGENT_TYPE_ARG)
                if call["name"] != TASK_TOOL or not isinstance(name, str) or not name:
                    continue
                if call_id and call_id in self._seen_task_calls:
                    continue
                if call_id:
                    self._seen_task_calls.add(call_id)
                self._pending_subagents.append(name)

    def _remember_resumed_subagent(self, ns: tuple[str, ...], mode: str, payload: object) -> None:
        """续跑时用历史 tool_call_id 把新的映射器接回原子图名称。"""
        if mode != "updates" or not isinstance(payload, dict):
            return
        segment = ns[-1]
        node, separator, task_uuid = segment.partition(":")
        if node != TOOLS_NODE or not separator or task_uuid in self._subagent_by_uuid:
            return
        for update in payload.values():
            if not isinstance(update, dict):
                continue
            messages = update.get("messages")
            if not isinstance(messages, list):
                continue
            for message in messages:
                if not isinstance(message, ToolMessage):
                    continue
                known = self._known_tool_paths.get(message.tool_call_id)
                if known:
                    self._subagent_by_uuid[task_uuid] = known[-1]
                    return

    def _map_path(self, ns: tuple[str, ...]) -> tuple[str, ...]:
        """把 ``tools:<uuid>`` 翻译成子智能体名，未知 uuid 保留八位前缀。"""
        path: list[str] = []
        for segment in ns:
            node, separator, task_uuid = segment.partition(":")
            if not separator:
                path.append(segment)
                continue
            if node == TOOLS_NODE and task_uuid not in self._subagent_by_uuid and self._pending_subagents:
                self._subagent_by_uuid[task_uuid] = self._pending_subagents.popleft()
            path.append(self._subagent_by_uuid.get(task_uuid, task_uuid[:8]))
        return tuple(path)


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
        traces = [*_map_compaction(update, stamp), *_map_todos(update, stamp)]
        events.extend(traces)
        # 只带状态痕迹（压缩、清单）、没有消息的更新是正常的，不按「载荷里没有 messages」
        # 告警。**豁免只给这两种** —— 其余没有 messages 的更新仍要告警，那是 DeepAgents
        # 换了结构的信号，静默掉就等于把它藏起来
        if traces and isinstance(update, dict) and "messages" not in update:
            continue
        events.extend(_map_node(str(node), update, stamp))
    return events


def _map_compaction(update: object, stamp: _Stamp) -> list[Event]:
    """压缩发生的那一轮，state 更新里会多出一条压缩痕迹。

    **这是平台唯一能看见压缩的地方。** 中间件把它写在私有 state 字段里，
    实测（2026-08-19 探针）它确实流得到 updates；阈值调高到不触发时这个键就不出现，
    因此「有这个键」等价于「这一轮压了一次」。
    """
    if not isinstance(update, dict):
        return []
    event = update.get(SUMMARIZATION_KEY)
    if not isinstance(event, dict):
        return []

    index = event.get("cutoff_index")
    path = event.get("file_path")
    if not isinstance(index, int) or index < 0:
        logger.warning("压缩痕迹里的 cutoff_index 不可用，已跳过：%r", index)
        return []
    return [
        CompactionEvent(
            ts=stamp.ts,
            run_id=stamp.run_id,
            path=stamp.path,
            data=CompactionData(cutoff_index=index, file_path=path if isinstance(path, str) else None),
        )
    ]


def _map_todos(update: object, stamp: _Stamp) -> list[Event]:
    """改过清单的那一轮，`tools` 节点的 update 里会多一个 `todos` 键。

    **形状与压缩痕迹同型**（2026-08-19 探针）：那个工具返回的是一条 `Command`，
    整张清单跟着 state 更新一起流到 `updates`。因此「有这个键」等价于
    「这一轮改过清单」，没改的轮次这个键根本不出现。

    **同一次调用还会照常产出一条 `tool_result`**，正文是英文的
    `Updated todo list to [...]` —— 那条不在这里拦掉：事件流是唯一真相源，
    删事件等于让重放看不见发生过什么。收编成一张卡片是前端的事。
    """
    if not isinstance(update, dict) or TODO_KEY not in update:
        return []
    todos = update[TODO_KEY]
    if not isinstance(todos, list):
        logger.warning("清单不是列表，已跳过：%s", type(todos).__name__)
        return []

    items: list[TodoItem] = []
    for one in todos:
        content = one.get("content") if isinstance(one, dict) else None
        status = one.get("status") if isinstance(one, dict) else None
        if not isinstance(content, str) or status not in TODO_STATUS:
            logger.warning("清单条目形状不认识，已跳过：%r", one)
            continue
        items.append(TodoItem(content=content, status=status))
    return [
        TodoUpdatedEvent(
            ts=stamp.ts,
            run_id=stamp.run_id,
            path=stamp.path,
            data=TodoUpdatedData(todos=items),
        )
    ]


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
    # 平台自己注入的状态块会跟着模型回复一起写回 state（尾部注入改成持久追加之后）。
    # **豁免只给它一种** —— 那条告警本来是「框架吐了没见过的形状」的信号，
    # 一刀切放行非 AIMessage 就等于把这个信号自己弄哑了
    if isinstance(message, HumanMessage) and str(message.content).startswith(BLOCK_HEADER):
        return []
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
