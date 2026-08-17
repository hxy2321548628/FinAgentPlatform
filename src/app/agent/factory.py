"""智能体的装配：把模型、提示词、沙箱 backend 拼成一个可驱动的 DeepAgents 图。

**本模块是执行器与 LangGraph 之间的唯一接触面。** 执行器只认三件事 —— 开跑、恢复、
问一句「有没有在等人确认」，不认识 graph、config、`Command` 这些框架概念，
换掉编排框架时改这里就够。

主图与子图都使用 DeepAgents 内置文件工具，并由同一个沙箱 backend 驱动；
子图自行编译，以便平台绑定独立递归上限。
"""

from collections.abc import AsyncIterator
from contextlib import nullcontext
from types import MappingProxyType
from typing import Protocol, cast

from deepagents import create_deep_agent
from deepagents.backends.protocol import BackendProtocol
from langchain.agents.middleware.human_in_the_loop import DecisionType, InterruptOnConfig
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langchain_deepseek import ChatDeepSeek
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command

from app.agent.config import AgentConfig
from app.agent.mcp import McpFailureRecorderProtocol, McpTargetLoaderProtocol, load_mcp_tools
from app.agent.prompt import compose_prompt
from app.agent.skill import PLATFORM_SKILLS_SYSTEM_PROMPT, ReloadingSkillsMiddleware
from app.agent.subagent import SubagentLoaderProtocol, compile_subagents
from app.agent.trace import attribution, propagation
from app.event.mapper import StreamChunk
from app.event.model import InterruptAction
from config import Settings

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


def create_model(settings: Settings, *, model_name: str | None = None) -> BaseChatModel:
    """按配置构造一个聊天模型，默认是主模型。

    Args:
        settings: 平台配置。
        model_name: 换成别的模型。网关起会话标题时给的是辅助模型 —— 概括一句话
            不需要主模型那份多步推理能力，而主模型贵一个数量级。

    Returns:
        可供 DeepAgents 使用的聊天模型。
    """
    return ChatDeepSeek(
        model_name=model_name or settings.model_main,
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

    def __init__(
        self,
        *,
        model: BaseChatModel,
        checkpointer: BaseCheckpointSaver[str],
        callback: BaseCallbackHandler | None = None,
        subagent_loader: SubagentLoaderProtocol | None = None,
        mcp_loader: McpTargetLoaderProtocol | None = None,
        mcp_recorder: McpFailureRecorderProtocol | None = None,
    ) -> None:
        self._model = model
        self._checkpointer = checkpointer
        self._callback = callback
        self._subagent_loader = subagent_loader
        self._mcp_loader = mcp_loader
        self._mcp_recorder = mcp_recorder

    def stream(
        self,
        backend: BackendProtocol,
        thread_id: str,
        content: str,
        agent_config: AgentConfig | None = None,
        *,
        user_id: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """第一次跑一个提问。"""
        return self._astream(
            backend,
            thread_id,
            {"messages": [{"role": "user", "content": content}]},
            agent_config,
            user_id=user_id,
        )

    def resume(
        self,
        backend: BackendProtocol,
        thread_id: str,
        decisions: list[dict[str, object]],
        agent_config: AgentConfig | None = None,
        *,
        user_id: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """带着教师的决策从中断点接着跑。

        **决策的顺序必须与 `action_requests` 对齐** —— 重排在 `run/approval.py` 里做完了。
        """
        return self._astream(
            backend,
            thread_id,
            Command(resume={RESUME_KEY: decisions}),
            agent_config,
            user_id=user_id,
        )

    async def pending(
        self, backend: BackendProtocol, thread_id: str, agent_config: AgentConfig | None = None
    ) -> list[InterruptAction]:
        """问一句「有没有在等人确认」。

        **查状态而不是查流**：中断让执行暂停、流自然结束，它不是流里的某个事件。
        查状态这条路两套 stream API 都成立，不依赖框架某个未确认的行为。

        Args:
            backend: 会话的沙箱 backend。
            thread_id: 会话标识。
            agent_config: 这次 run 的配置快照。

        Returns:
            待确认的调用，按 index 排列；没有中断则空列表。
        """
        # **这一步不装外部工具。** 中断记在 checkpoint 里，读它与图上绑了哪些工具无关；
        # 而装一遍就是一次外网往返 —— 每条 run 流跑完都要查一次中断，不去掉的话
        # 挂了 MCP 的分析每次都连两遍那台校外机器（实测日志里两条装配相隔 8 秒），
        # 而每一次都可能失败、都会记进熔断计数
        snapshot = await (await self._graph(backend, agent_config, with_mcp=False)).aget_state(self._config(thread_id))
        return _actions(getattr(snapshot, "interrupts", ()))

    def _astream(
        self,
        backend: BackendProtocol,
        thread_id: str,
        entry: dict[str, object] | Command[object],
        agent_config: AgentConfig | None,
        *,
        user_id: str | None,
    ) -> AsyncIterator[StreamChunk]:
        async def stream() -> AsyncIterator[StreamChunk]:
            graph = await self._graph(backend, agent_config)
            # **身份要在这里再挂一次，`metadata` 那两个键不够。** 回调只把它们挂到
            # 根 span 上，而模型是在 LangGraph 随后开出的 async 任务里调的 ——
            # token 因此全落在没有主人的 GENERATION 上，按用户切出来每人都是 0。
            # 没配 Langfuse 时不进：`propagate_attributes` 要一个构造过的全局客户端
            tracing = propagation(thread_id=thread_id, user_id=user_id) if self._callback else nullcontext()
            with tracing:
                async for chunk in graph.astream(
                    entry,
                    self._config(thread_id, user_id=user_id),
                    stream_mode=STREAM_MODE,
                    subgraphs=True,
                ):
                    yield chunk

        return stream()

    async def _graph(
        self,
        backend: BackendProtocol,
        agent_config: AgentConfig | None = None,
        *,
        with_mcp: bool = True,
    ) -> SupportsAgent:
        # LangGraph 的 astream 按 stream_mode 的字面量类型分重载，表达不了
        # 「传 list 且 subgraphs=True 时逐个吐 (ns, mode, payload) 三元组」这个组合，
        # 于是收窄成本模块自己的 Protocol。三元组的形状由入库的真实 chunk 钉住。
        # **不挂 MCP 的 run 一个额外动作都不做。** 绝大多数分析走的是这条路，
        # 而「平台好像变慢了」不会有任何日志指向外网往返
        mcp_tools = await self._mcp_tools(agent_config) if with_mcp else []
        subagents = None
        if agent_config is not None and agent_config.subagents:
            if self._subagent_loader is None:
                raise RuntimeError("运行快照包含子智能体，但 worker 未配置子智能体仓储")
            subagents = await compile_subagents(
                agent_config.subagents,
                loader=self._subagent_loader,
                model=self._model,
                backend=backend,
                tools=mcp_tools,
            )
        return cast(
            SupportsAgent,
            create_deep_agent(
                model=self._model,
                tools=mcp_tools,
                backend=backend,
                system_prompt=compose_prompt(agent_config),
                checkpointer=self._checkpointer,
                subagents=subagents,
                middleware=[
                    ReloadingSkillsMiddleware(
                        backend=backend,
                        sources=[("/workspace/skill/", "平台")],
                        system_prompt=PLATFORM_SKILLS_SYSTEM_PROMPT,
                    )
                ],
                # `MappingProxyType` 是为了不构成可变全局状态，交出去时复制一份
                interrupt_on=dict(INTERRUPT_ON),
            ),
        )

    async def _mcp_tools(self, agent_config: AgentConfig | None) -> list[BaseTool]:
        if agent_config is None or not agent_config.mcps:
            return []
        if self._mcp_loader is None:
            raise RuntimeError("运行快照包含 MCP 引用，但 worker 未配置 MCP 目录仓储")
        return await load_mcp_tools(
            agent_config.mcps,
            loader=self._mcp_loader,
            recorder=self._mcp_recorder,
        )

    def _config(self, thread_id: str, *, user_id: str | None = None) -> dict[str, object]:
        config: dict[str, object] = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": RECURSION_LIMIT,
        }
        # 没配 Langfuse 时连 metadata 都不放：那几个键对 LangGraph 毫无意义，
        # 而一个总是带着陌生键的 config 会让排障时多一个「这是干嘛的」
        if self._callback is not None:
            config["callbacks"] = [self._callback]
            config["metadata"] = attribution(thread_id=thread_id, user_id=user_id)
        return config


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
