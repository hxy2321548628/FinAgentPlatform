"""把运行快照里的子智能体引用编译成独立、受限的 LangGraph runnable。"""

from dataclasses import dataclass
from typing import Any, Protocol

from deepagents import CompiledSubAgent
from deepagents.backends.protocol import BackendProtocol
from deepagents.middleware.filesystem import FilesystemMiddleware
from deepagents.middleware.patch_tool_calls import PatchToolCallsMiddleware
from deepagents.middleware.summarization import create_summarization_middleware
from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.human_in_the_loop import HumanInTheLoopMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool

from agent.config import SubagentReference
from agent.prompt import ENVIRONMENT_SEGMENT

# 子智能体单独计图步数。与主图一样留够正常分析余量，同时避免上游默认的 9999
# 让一个跑飞的子图烧掉数千次主模型调用。
SUBAGENT_RECURSION_LIMIT = 60
MAX_SUBAGENT = 5


@dataclass(frozen=True)
class SubagentDefinition:
    """按冻结版本读出的子智能体执行内容。"""

    description: str
    system_prompt: str


class SubagentLoaderProtocol(Protocol):
    """执行侧读取冻结版本所需的最小仓储接口。"""

    async def load_subagent(self, agent_id: str, version: int) -> SubagentDefinition | None:
        """按稳定标识与版本号读取内容，不重新判断当前可见性。"""
        ...


class SubagentSnapshotError(RuntimeError):
    """快照指向的版本已经无法读取。"""


async def compile_subagents(
    references: list[SubagentReference],
    *,
    loader: SubagentLoaderProtocol,
    model: BaseChatModel,
    backend: BackendProtocol,
    tools: list[BaseTool] | None = None,
) -> list[CompiledSubAgent]:
    """按快照顺序编译子智能体。

    `CompiledSubAgent` 不会获得声明式 spec 的自动工具继承，因此文件工具、摘要、
    工具调用修补与 HITL 都在这里显式装配。名称取冻结快照，避免作者改名后历史 run
    的 `task` 名称发生变化；提示词则按冻结版本读取。

    Args:
        references: 快照里冻结的子智能体。
        loader: 读取冻结版本的仓储。
        model: 主模型，子智能体与主图共用。
        backend: 会话的沙箱 backend，主图与子图共享同一个工作目录。
        tools: 外部工具（MCP）。子智能体与主图拿到的是同一批 —— 一次分析勾了哪些
            外部服务是一次 run 的属性，不是某一层 agent 的属性。
    """
    compiled: list[CompiledSubAgent] = []
    for reference in references:
        definition = await loader.load_subagent(reference.agent_id, reference.version)
        if definition is None:
            raise SubagentSnapshotError(
                f"子智能体快照无法读取：agent_id={reference.agent_id} version={reference.version}"
            )
        prompt = "\n\n".join((definition.system_prompt, ENVIRONMENT_SEGMENT))
        middleware: list[AgentMiddleware[Any, Any, Any]] = [
            FilesystemMiddleware(backend=backend),
            create_summarization_middleware(model, backend),
            PatchToolCallsMiddleware(),
            HumanInTheLoopMiddleware(
                interrupt_on={"delete": {"allowed_decisions": ["approve", "reject", "edit", "respond"]}}
            ),
        ]
        runnable = create_agent(
            model,
            tools=list(tools or []),
            system_prompt=prompt,
            middleware=middleware,
            name=reference.name,
        ).with_config({"recursion_limit": SUBAGENT_RECURSION_LIMIT})
        compiled.append(
            CompiledSubAgent(
                name=reference.name,
                description=definition.description,
                runnable=runnable,
            )
        )
    return compiled
