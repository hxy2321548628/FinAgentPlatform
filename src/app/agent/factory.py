"""智能体的装配：把模型、提示词、沙箱 backend 拼成一个可驱动的 DeepAgents 图。

**本模块是执行器与 LangGraph 之间的唯一接触面。** 执行器只认三件事 —— 开跑、恢复、
问一句「有没有在等人确认」，不认识 graph、config、`Command` 这些框架概念，
换掉编排框架时改这里就够。

主图与子图都使用 DeepAgents 内置文件工具，并由同一个沙箱 backend 驱动；
子图自行编译，以便平台绑定独立递归上限。
"""

from collections.abc import AsyncIterator
from contextlib import nullcontext
from typing import Any, Protocol, cast

from deepagents import create_deep_agent
from deepagents.backends.protocol import BackendProtocol
from langchain.agents.middleware import AgentMiddleware
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langchain_deepseek import ChatDeepSeek
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command

from app.agent.config import AgentConfig
from app.agent.context import (
    CONTEXT_TRIGGER_TOKEN,
    TOOL_RESULT_EVICT_TOKEN,
    create_offloader,
    create_squeezer,
)
from app.agent.interrupt import ALLOWED_DECISION, DELETE_TOOL, INTERRUPT_ON
from app.agent.mcp import McpFailureRecorderProtocol, McpTargetLoaderProtocol, load_mcp_tools
from app.agent.prompt import compose_prompt
from app.agent.question import create_question_tool
from app.agent.skill import PLATFORM_SKILLS_SYSTEM_PROMPT, ReloadingSkillsMiddleware
from app.agent.subagent import SubagentLoaderProtocol, compile_subagents
from app.agent.tail import InstalledPackageSection, StepBudgetSection, TailContextMiddleware
from app.agent.todo import create_todo_middleware
from app.agent.trace import attribution, propagation
from app.event.mapper import StreamChunk
from app.event.model import InterruptAction
from config import Settings

# 一次分析实测 17 轮模型调用、16 次工具调用，图上的步数约为其两倍。
# 取 60 是留够余量又不至于让跑飞的 agent 无限烧 token。
# **这是默认值，真正生效的是 Settings 里那一项** —— 调到极小值才验得出「撞上限记成哪个码」
RECURSION_LIMIT = 60

# 三个模式缺一不可：token 与 reasoning 增量在 messages，工具调用与结果在 updates，
# custom 留给工具自己写的事件
STREAM_MODE = ["updates", "messages", "custom"]

# 中断配置在 app.agent.interrupt：子图要装同一份，而本模块 import 子图模块，
# 反过来 import 会成环。改拦截范围去那里改，别在这里再写一份

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
        recursion_limit: int = RECURSION_LIMIT,
        context_trigger_token: int = CONTEXT_TRIGGER_TOKEN,
        tool_result_evict_token: int = TOOL_RESULT_EVICT_TOKEN,
    ) -> None:
        self._model = model
        self._checkpointer = checkpointer
        self._recursion_limit = recursion_limit
        self._context_trigger_token = context_trigger_token
        self._tool_result_evict_token = tool_result_evict_token
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
                # **提问工具与 MCP 工具排在一起，但它不是可选的** —— 它是 `INTERRUPT_ON`
                # 里那三个键之一，装不上的话模型调用它只会得到「没有这个工具」，
                # 而那种失败看着像模型胡编了一个工具名
                tools=[create_question_tool(), *mcp_tools],
                backend=backend,
                system_prompt=compose_prompt(agent_config),
                checkpointer=self._checkpointer,
                subagents=subagents,
                middleware=self._middleware(backend),
                # `MappingProxyType` 是为了不构成可变全局状态，交出去时复制一份
                interrupt_on=dict(INTERRUPT_ON),
            ),
        )

    def _middleware(self, backend: BackendProtocol) -> list[AgentMiddleware[Any, Any, Any]]:
        """本平台往 DeepAgents 的基础栈里加的那几个中间件。

        **压缩那一份是按名替换基础栈里的默认份**（deepagents 按 `.name` 合并自定义中间件），
        不是再叠一套 —— 两套压缩都会改写历史，谁先触发不确定，而且都会打掉前缀缓存。
        """
        return [
            ReloadingSkillsMiddleware(
                backend=backend,
                sources=[("/workspace/skill/", "平台")],
                system_prompt=PLATFORM_SKILLS_SYSTEM_PROMPT,
            ),
            # **只装主图。** 清单是给教师看的单一进度，子图再来一张就是两个真相源，
            # 而前端还要回答「哪张是当前的」。它注入的是静态 prose，前缀仍逐字节稳定
            create_todo_middleware(),
            create_squeezer(self._model, backend, trigger_token=self._context_trigger_token),
            # **大工具结果挪到磁盘**，模型只看到一句路径。不挪的话它整段留在历史里，
            # 此后每一轮都按未命中价重算一遍 —— 首轮实测最贵那题因此烧掉 12.5 万 token
            create_offloader(backend, evict_token=self._tool_result_evict_token),
            # **每轮都变的内容一律走这里**，不许进系统提示词 —— 落进前缀就是每轮
            # 打掉整段 prompt cache，而平台的价签是命中与不命中差 30 倍
            TailContextMiddleware(
                sections=[
                    StepBudgetSection(limit=self._recursion_limit),
                    InstalledPackageSection(),
                ]
            ),
        ]

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
            "recursion_limit": self._recursion_limit,
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
