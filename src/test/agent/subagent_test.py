"""子智能体独立图的装配测试。"""

from typing import Any, cast

import pytest
from deepagents.middleware.filesystem import FilesystemMiddleware
from deepagents.middleware.patch_tool_calls import PatchToolCallsMiddleware
from langchain.agents.middleware.human_in_the_loop import HumanInTheLoopMiddleware
from langchain_core.language_models import BaseChatModel

from app.agent.config import SubagentReference
from app.agent.prompt import ENVIRONMENT_SEGMENT
from app.agent.subagent import (
    SUBAGENT_RECURSION_LIMIT,
    SubagentDefinition,
    SubagentSnapshotError,
    compile_subagents,
)


class DummyModel(BaseChatModel):
    @property
    def _llm_type(self) -> str:
        return "dummy"

    def _generate(self, *argument: Any, **keyword: Any) -> Any:  # noqa: ANN401 - 抽象方法占位
        raise NotImplementedError


class FakeBackend:
    pass


class Loader:
    def __init__(self, definition: SubagentDefinition | None) -> None:
        self.definition = definition
        self.calls: list[tuple[str, int]] = []

    async def load_subagent(self, agent_id: str, version: int) -> SubagentDefinition | None:
        self.calls.append((agent_id, version))
        return self.definition


class Runnable:
    def __init__(self) -> None:
        self.config: dict[str, object] = {}

    def with_config(self, config: dict[str, object]) -> "Runnable":
        self.config = config
        return self


async def test_a_compiled_subagent_uses_the_frozen_version_and_platform_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: dict[str, Any] = {}
    runnable = Runnable()

    def fake_create_agent(*argument: Any, **keyword: Any) -> Runnable:  # noqa: ANN401 - 替身照单全收
        created["argument"] = argument
        created.update(keyword)
        return runnable

    monkeypatch.setattr("app.agent.subagent.create_agent", fake_create_agent)
    loader = Loader(SubagentDefinition(description="专门计算波动率", system_prompt="只计算波动率。"))
    backend = FakeBackend()
    reference = SubagentReference(agent_id="agent-1", version=3, name="volatility-expert")

    compiled = await compile_subagents(
        [reference],
        loader=loader,
        model=DummyModel(),
        backend=backend,  # type: ignore[arg-type]
    )

    assert loader.calls == [("agent-1", 3)]
    assert compiled[0]["name"] == "volatility-expert"
    assert compiled[0]["description"] == "专门计算波动率"
    assert cast(object, compiled[0]["runnable"]) is runnable
    assert created["system_prompt"] == f"只计算波动率。\n\n{ENVIRONMENT_SEGMENT}"
    assert runnable.config == {"recursion_limit": SUBAGENT_RECURSION_LIMIT}

    middleware = created["middleware"]
    filesystem = next(one for one in middleware if isinstance(one, FilesystemMiddleware))
    assert cast(object, filesystem.backend) is backend
    assert {tool.name for tool in filesystem.tools} == {
        "ls",
        "read_file",
        "write_file",
        "edit_file",
        "delete",
        "glob",
        "grep",
        "execute",
    }
    assert any(isinstance(one, PatchToolCallsMiddleware) for one in middleware)
    assert any(isinstance(one, HumanInTheLoopMiddleware) for one in middleware)


async def test_a_missing_frozen_version_fails_instead_of_falling_back() -> None:
    reference = SubagentReference(agent_id="agent-1", version=9, name="missing")

    with pytest.raises(SubagentSnapshotError, match="version=9"):
        await compile_subagents(
            [reference],
            loader=Loader(None),
            model=DummyModel(),
            backend=FakeBackend(),  # type: ignore[arg-type]
        )


async def test_the_bound_limit_stops_a_real_looping_subgraph(tmp_path: pytest.TempPathFactory) -> None:
    """P9④：真实图应在平台额度停下，而不是落回 DeepAgents 的 9999。"""
    from collections.abc import Callable, Sequence

    from deepagents.backends import FilesystemBackend
    from langchain_core.language_models.base import LanguageModelInput
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, ChatResult
    from langchain_core.runnables import Runnable
    from langchain_core.tools import BaseTool
    from langgraph.errors import GraphRecursionError

    class LoopModel(BaseChatModel):
        calls: int = 0

        @property
        def _llm_type(self) -> str:
            return "loop"

        def bind_tools(
            self,
            tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],
            *,
            tool_choice: str | None = None,
            **kwargs: Any,  # noqa: ANN401 - 必须匹配 LangChain 抽象签名
        ) -> Runnable[LanguageModelInput, AIMessage]:
            return self

        def _generate(self, *argument: Any, **keyword: Any) -> ChatResult:  # noqa: ANN401 - 基类参数繁杂
            self.calls += 1
            message = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "write_file",
                        "args": {"file_path": "/workspace/loop.txt", "content": "x"},
                        "id": f"loop-{self.calls}",
                        "type": "tool_call",
                    }
                ],
            )
            return ChatResult(generations=[ChatGeneration(message=message)])

    model = LoopModel()
    reference = SubagentReference(agent_id="agent-1", version=1, name="loop")
    compiled = await compile_subagents(
        [reference],
        loader=Loader(SubagentDefinition(description="循环", system_prompt="一直调用工具")),
        model=model,
        backend=FilesystemBackend(root_dir=str(tmp_path), virtual_mode=True),
    )

    with pytest.raises(GraphRecursionError, match=rf"{SUBAGENT_RECURSION_LIMIT}"):
        compiled[0]["runnable"].invoke({"messages": [{"role": "user", "content": "开始"}]})

    assert model.calls < SUBAGENT_RECURSION_LIMIT
