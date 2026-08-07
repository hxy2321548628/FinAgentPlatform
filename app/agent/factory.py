"""智能体的装配：把模型、提示词、沙箱 backend 拼成一个可驱动的 DeepAgents 图。

**本模块是执行器与 LangGraph 之间的唯一接触面。** 执行器只认三件事 —— 开跑、恢复、
问一句「有没有在等人确认」，不认识 graph、config、`Command` 这些框架概念，
换掉编排框架时改这里就够。

本期是单 agent、无子 agent：工具集就是 DeepAgents 内置的 8 个，
只把驱动它们的 backend 换成沙箱的实现。
"""

from collections.abc import AsyncIterator
from types import MappingProxyType
from typing import Protocol, cast

from deepagents import create_deep_agent
from deepagents.backends.protocol import BackendProtocol
from langchain.agents.middleware.human_in_the_loop import DecisionType, InterruptOnConfig
from langchain_core.language_models import BaseChatModel
from langchain_deepseek import ChatDeepSeek
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command

from agent.prompt import SYSTEM_PROMPT
from config import Settings
from event.mapper import StreamChunk
from event.model import InterruptAction

# 一次分析实测 17 轮模型调用、16 次工具调用，图上的步数约为其两倍。
# 取 60 是留够余量又不至于让跑飞的 agent 无限烧 token
RECURSION_LIMIT = 60

# 三个模式缺一不可：token 与 reasoning 增量在 messages，工具调用与结果在 updates，
# custom 留给工具自己写的事件
STREAM_MODE = ["updates", "messages", "custom"]

# **只全量拦 `delete`，不写任何 `when` 谓词。**
#
# P0 实测一次完整分析里 agent 调了 16 次工具，`delete` 一次都没调 —— 低频高危，
# 全量拦不伤可用性。反过来，若给 `execute` 全量加审批，那一次分析就要教师点十几次确认，
# 平台会变得没法用。
#
# > **将来加 `execute` 的条件拦截时，`when` 谓词必须是工具调用的纯函数。**
# > 多个 interrupt 靠**位置索引**匹配 resume 值，官方明确警告：非确定性逻辑会破坏
# > 基于索引的匹配。「代码涉及删除文件时拦截」只看 args，安全；
# > 「预估 token 超阈值时拦截」若掺入外部状态或时间，重放时索引就会错位 ——
# > 而它坏掉的方式是静默的：把 A 的决策套到 B 的调用上。
# >
# > **加它之前先补上观察项**：量一次真实分析里谓词命中几次。命中 0 次说明太严，
# > 命中十几次说明平台没法用，不量就定是在猜。
DELETE_TOOL = "delete"

ALLOWED_DECISION: tuple[DecisionType, ...] = ("approve", "reject", "edit", "respond")

INTERRUPT_ON: MappingProxyType[str, InterruptOnConfig] = MappingProxyType(
    {DELETE_TOOL: InterruptOnConfig(allowed_decisions=list(ALLOWED_DECISION))}
)

RESUME_KEY = "decisions"


class SupportsAgent(Protocol):
    """本模块对编译好的图的全部要求。"""

    def astream(
        self,
        input: dict[str, object] | Command[object],
        config: dict[str, object],
        *,
        stream_mode: list[str],
        subgraphs: bool,
    ) -> AsyncIterator[StreamChunk]:
        """按 (ns, mode, payload) 三元组流式产出执行过程。"""
        ...

    async def aget_state(self, config: dict[str, object]) -> object:
        """取当前的图状态快照。"""
        ...


def create_model(settings: Settings) -> BaseChatModel:
    """按配置构造主模型。

    Args:
        settings: 平台配置。

    Returns:
        可供 DeepAgents 使用的聊天模型。
    """
    return ChatDeepSeek(
        model_name=settings.model_main,
        api_key=settings.deepseek_api_key,
        api_base=settings.deepseek_base_url,
        # 同一份数据同一个问题应该给出同一套算法，分析任务不需要发散
        temperature=0,
    )


class Agent:
    """驱动一次分析的三件事：开跑、恢复、问有没有在等人确认。

    每次调用都新建一个图，因为 backend 是按会话绑定的；checkpointer 则共享，
    会话历史与中断状态都靠它按 `thread_id` 隔离 —— **checkpointer 是 HITL 的硬前提**。

    Args:
        model: 主模型。
        checkpointer: 会话状态的持久化。
    """

    def __init__(self, *, model: BaseChatModel, checkpointer: BaseCheckpointSaver[str]) -> None:
        self._model = model
        self._checkpointer = checkpointer

    def stream(self, backend: BackendProtocol, thread_id: str, content: str) -> AsyncIterator[StreamChunk]:
        """第一次跑一个提问。"""
        return self._astream(backend, thread_id, {"messages": [{"role": "user", "content": content}]})

    def resume(
        self, backend: BackendProtocol, thread_id: str, decisions: list[dict[str, object]]
    ) -> AsyncIterator[StreamChunk]:
        """带着教师的决策从中断点接着跑。

        **决策的顺序必须与 `action_requests` 对齐** —— 重排在 `run/approval.py` 里做完了。
        """
        return self._astream(backend, thread_id, Command(resume={RESUME_KEY: decisions}))

    async def pending(self, backend: BackendProtocol, thread_id: str) -> list[InterruptAction]:
        """问一句「有没有在等人确认」。

        **查状态而不是查流**：中断让执行暂停、流自然结束，它不是流里的某个事件。
        查状态这条路两套 stream API 都成立，不依赖框架某个未确认的行为。

        Args:
            backend: 会话的沙箱 backend。
            thread_id: 会话标识。

        Returns:
            待确认的调用，按 index 排列；没有中断则空列表。
        """
        snapshot = await self._graph(backend).aget_state(self._config(thread_id))
        return _actions(getattr(snapshot, "interrupts", ()))

    def _astream(
        self, backend: BackendProtocol, thread_id: str, entry: dict[str, object] | Command[object]
    ) -> AsyncIterator[StreamChunk]:
        return self._graph(backend).astream(
            entry,
            self._config(thread_id),
            stream_mode=STREAM_MODE,
            subgraphs=True,
        )

    def _graph(self, backend: BackendProtocol) -> SupportsAgent:
        # LangGraph 的 astream 按 stream_mode 的字面量类型分重载，表达不了
        # 「传 list 且 subgraphs=True 时逐个吐 (ns, mode, payload) 三元组」这个组合，
        # 于是收窄成本模块自己的 Protocol。三元组的形状由入库的真实 chunk 钉住。
        return cast(
            SupportsAgent,
            create_deep_agent(
                model=self._model,
                backend=backend,
                system_prompt=SYSTEM_PROMPT,
                checkpointer=self._checkpointer,
                # `MappingProxyType` 是为了不构成可变全局状态，交出去时复制一份
                interrupt_on=dict(INTERRUPT_ON),
            ),
        )

    def _config(self, thread_id: str) -> dict[str, object]:
        return {"configurable": {"thread_id": thread_id}, "recursion_limit": RECURSION_LIMIT}


def _actions(interrupts: object) -> list[InterruptAction]:
    """把 LangGraph 的 `Interrupt` 摊平成平台的形状。

    DeepAgents 给的是 `action_requests` 与 `review_configs` 两个平行数组，
    这里合并成一个并加上 index。形状不认识时按「没有中断」处理 ——
    宁可让 run 正常跑完，也不要因为读不懂一个中断就把整次分析掀掉。
    """
    if not isinstance(interrupts, tuple | list):
        return []
    found: list[InterruptAction] = []
    for one in interrupts:
        value = getattr(one, "value", None)
        if not isinstance(value, dict):
            continue
        requests = value.get("action_requests")
        configs = value.get("review_configs")
        if not isinstance(requests, list):
            continue
        allowed = _allowed(configs)
        for request in requests:
            if not isinstance(request, dict):
                continue
            name = str(request.get("name", ""))
            args = request.get("args")
            found.append(
                InterruptAction(
                    index=len(found),
                    tool_name=name or DELETE_TOOL,
                    args=args if isinstance(args, dict) else {},
                    allowed_decisions=allowed.get(name, list(ALLOWED_DECISION)),
                )
            )
    return found


def _allowed(configs: object) -> dict[str, list[str]]:
    if not isinstance(configs, list):
        return {}
    table: dict[str, list[str]] = {}
    for one in configs:
        if not isinstance(one, dict):
            continue
        name = one.get("action_name")
        decisions = one.get("allowed_decisions")
        if isinstance(name, str) and isinstance(decisions, list):
            table[name] = [str(decision) for decision in decisions]
    return table
