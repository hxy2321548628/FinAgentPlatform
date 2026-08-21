"""供 ``langgraph dev`` 使用的真实 broker/沙箱图入口。

开发服务器只负责驱动 LangGraph 图；本入口负责把每个线程接到项目的 broker，
并在一次 run 的生命周期内申请、归还真实沙箱。只在执行上下文创建外部资源，
Studio 读取图结构时使用轻量的状态后端，不会误起沙箱。
"""

from collections.abc import AsyncGenerator, Mapping
from contextlib import asynccontextmanager
from uuid import uuid4

from deepagents.backends import StateBackend
from langchain_core.runnables import RunnableConfig
from langgraph_sdk.runtime import ServerRuntime

from app.agent.factory import Agent, SupportsAgent, create_model
from app.sandbox.remote import (
    BrokerConnection,
    RemoteBackendFactory,
    RemoteSandboxPool,
    RemoteWorkspace,
)
from config import Settings, get_settings

SCHEMA_THREAD_ID = "00000000000000000000000000000000"


@asynccontextmanager
async def make_graph(config: RunnableConfig, runtime: ServerRuntime) -> AsyncGenerator[SupportsAgent]:
    """构造一张开发图，并把真实沙箱绑定到当前 LangGraph 线程。

    ``langgraph dev`` 会在退出这个异步上下文时结束本次 run，因此沙箱租约放在
    同一个上下文里，遇到模型异常或人工中断也能归还。持久化由
    ``langgraph.json`` 中的 checkpointer 配置负责，图本身不绑定 saver。
    """
    settings = get_settings()
    is_execution = runtime.access_context == "threads.create_run"
    thread_id = _thread_id(config, runtime)
    if not is_execution:
        # 图结构、输入 schema 和状态读取不需要连接 broker；保持同一套 Agent 装配，
        # 但不为 Studio 的 introspection 启动容器。
        yield await _build_agent(settings).build_graph(StateBackend(), with_mcp=False)
        return

    connection = BrokerConnection(base_url=settings.broker_url)
    backend_factory = RemoteBackendFactory(base_url=settings.broker_url)
    workspace = RemoteWorkspace(connection)
    pool = RemoteSandboxPool(connection)
    holder = str(config.get("run_id") or uuid4().hex)
    acquired = False

    try:
        await workspace.create(thread_id)
        await pool.acquire(thread_id, holder=holder)
        acquired = True
        backend = backend_factory(thread_id)
        graph = await _build_agent(settings).build_graph(backend, with_mcp=False)
        yield graph
    finally:
        try:
            if acquired:
                await pool.release(thread_id, holder=holder)
        finally:
            try:
                await backend_factory.aclose()
            finally:
                await connection.aclose()


def _build_agent(settings: Settings) -> Agent:
    """复用生产图的提示词、中间件和人工审批配置。"""
    return Agent(
        model=create_model(settings),
        # Agent Server 会在图返回后注入 langgraph.json 指定的 checkpointer。
        checkpointer=None,
        recursion_limit=settings.agent_recursion_limit,
        context_trigger_token=settings.agent_context_trigger_token,
        tool_result_evict_token=settings.agent_tool_result_evict_token,
    )


def _thread_id(config: RunnableConfig, runtime: ServerRuntime) -> str:
    """从 Agent Server 配置取线程号；图结构读取没有线程号时使用固定占位目录。"""
    configurable = config.get("configurable")
    if isinstance(configurable, Mapping):
        value = configurable.get("thread_id")
        if value:
            thread_id = str(value)
            if "/" not in thread_id and thread_id not in {".", ".."}:
                return thread_id

    if runtime.access_context != "threads.create_run":
        return SCHEMA_THREAD_ID
    raise ValueError("真实执行缺少 thread_id，请通过 LangGraph runs API 创建线程后再运行")
