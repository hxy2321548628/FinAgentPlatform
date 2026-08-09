"""智能体的装配：把模型、提示词、沙箱 backend 拼成一个可驱动的 DeepAgents 图。

**本模块是执行器与 LangGraph 之间的唯一接触面。** 执行器只拿到一个「给我 chunk 流」的
函数，不认识 graph、config、stream_mode 这些框架概念 —— 换掉编排框架时改这里就够。

本期是单 agent、无子 agent、无 HITL：工具集就是 DeepAgents 内置的 8 个，
只把驱动它们的 backend 换成沙箱的实现。
"""

from collections.abc import AsyncIterator, Callable
from typing import Protocol, cast

from deepagents import create_deep_agent
from deepagents.backends.protocol import BackendProtocol
from langchain_core.language_models import BaseChatModel
from langchain_deepseek import ChatDeepSeek
from langgraph.checkpoint.base import BaseCheckpointSaver

from agent.prompt import SYSTEM_PROMPT
from config import Settings
from event.mapper import StreamChunk

# 一次分析实测 17 轮模型调用、16 次工具调用，图上的步数约为其两倍。
# 取 60 是留够余量又不至于让跑飞的 agent 无限烧 token
RECURSION_LIMIT = 60

# 三个模式缺一不可：token 与 reasoning 增量在 messages，工具调用与结果在 updates，
# custom 留给工具自己写的事件
STREAM_MODE = ["updates", "messages", "custom"]

type AgentRunner = Callable[[BackendProtocol, str, str], AsyncIterator[StreamChunk]]


class SupportsAstream(Protocol):
    """本模块对编译好的图的全部要求。"""

    def astream(
        self,
        input: dict[str, object],
        config: dict[str, object],
        *,
        stream_mode: list[str],
        subgraphs: bool,
    ) -> AsyncIterator[StreamChunk]:
        """按 (ns, mode, payload) 三元组流式产出执行过程。"""
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


def create_runner(*, model: BaseChatModel, checkpointer: BaseCheckpointSaver[str]) -> AgentRunner:
    """造一个「跑一次提问、产出 chunk 流」的函数。

    每次调用都新建一个图，因为 backend 是按 thread 绑定的；checkpointer 则共享，
    会话历史靠它按 `thread_id` 隔离。

    Args:
        model: 主模型。
        checkpointer: 会话状态的持久化，本期是内存实现。

    Returns:
        接收 (backend, thread_id, content) 并返回 chunk 流的函数。
    """

    def run(backend: BackendProtocol, thread_id: str, content: str) -> AsyncIterator[StreamChunk]:
        # LangGraph 的 astream 按 stream_mode 的字面量类型分重载，表达不了
        # 「传 list 且 subgraphs=True 时逐个吐 (ns, mode, payload) 三元组」这个组合，
        # 于是收窄成本模块自己的 Protocol。三元组的形状由入库的真实 chunk 钉住。
        agent = cast(
            SupportsAstream,
            create_deep_agent(
                model=model,
                backend=backend,
                system_prompt=SYSTEM_PROMPT,
                checkpointer=checkpointer,
            ),
        )
        return agent.astream(
            {"messages": [{"role": "user", "content": content}]},
            {"configurable": {"thread_id": thread_id}, "recursion_limit": RECURSION_LIMIT},
            stream_mode=STREAM_MODE,
            subgraphs=True,
        )

    return run
