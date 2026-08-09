"""智能体装配的测试。

这里只验装配参数是否按设计传下去，不跑真实模型 —— CI 里没有凭据，也不该花钱。
"""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from deepagents.backends.protocol import BackendProtocol
from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import SecretStr

from agent.factory import RECURSION_LIMIT, STREAM_MODE, create_model, create_runner
from agent.prompt import SYSTEM_PROMPT
from config import Settings
from event.mapper import StreamChunk


class RecordingAgent:
    """记录 astream 收到了什么的假图。"""

    def __init__(self) -> None:
        self.call: dict[str, Any] = {}

    def astream(
        self,
        input: dict[str, object],
        config: dict[str, object],
        *,
        stream_mode: list[str],
        subgraphs: bool,
    ) -> AsyncIterator[StreamChunk]:
        self.call = {
            "input": input,
            "config": config,
            "stream_mode": stream_mode,
            "subgraphs": subgraphs,
        }

        async def empty() -> AsyncIterator[StreamChunk]:
            return
            yield  # pragma: no cover - 让函数成为异步生成器

        return empty()


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> tuple[RecordingAgent, dict[str, Any]]:
    agent = RecordingAgent()
    built: dict[str, Any] = {}

    def fake_create_deep_agent(**argument: Any) -> RecordingAgent:  # noqa: ANN401 - 替身要照单全收
        built.update(argument)
        return agent

    monkeypatch.setattr("agent.factory.create_deep_agent", fake_create_deep_agent)
    return agent, built


class DummyModel(BaseChatModel):
    """只为占住 model 参数，不会被调用。"""

    @property
    def _llm_type(self) -> str:
        return "dummy"

    def _generate(self, *argument: Any, **keyword: Any) -> Any:  # noqa: ANN401 - 抽象方法的占位实现
        raise NotImplementedError


async def drain(stream: AsyncIterator[StreamChunk]) -> None:
    async for _ in stream:
        pass


class FakeBackend:
    pass


async def test_the_agent_is_built_with_the_platform_prompt(recorded: tuple[RecordingAgent, dict[str, Any]]) -> None:
    _, built = recorded
    runner = create_runner(model=DummyModel(), checkpointer=InMemorySaver())

    await drain(runner(FakeBackend(), "thread-1", "算个波动率"))  # type: ignore[arg-type]

    assert built["system_prompt"] == SYSTEM_PROMPT


async def test_the_sandbox_backend_drives_the_builtin_tools(recorded: tuple[RecordingAgent, dict[str, Any]]) -> None:
    """本期不自定义工具，只换驱动内置工具的后端 —— 传错这个参数文件就落进 LangGraph state 了。"""
    _, built = recorded
    backend: BackendProtocol = FakeBackend()  # type: ignore[assignment]
    runner = create_runner(model=DummyModel(), checkpointer=InMemorySaver())

    await drain(runner(backend, "thread-1", "一"))

    assert built["backend"] is backend


async def test_the_thread_id_isolates_conversation_history(
    recorded: tuple[RecordingAgent, dict[str, Any]],
) -> None:
    agent, _ = recorded
    runner = create_runner(model=DummyModel(), checkpointer=InMemorySaver())

    await drain(runner(FakeBackend(), "thread-42", "一"))  # type: ignore[arg-type]

    assert agent.call["config"]["configurable"]["thread_id"] == "thread-42"


async def test_the_question_is_sent_as_a_user_message(recorded: tuple[RecordingAgent, dict[str, Any]]) -> None:
    agent, _ = recorded
    runner = create_runner(model=DummyModel(), checkpointer=InMemorySaver())

    await drain(runner(FakeBackend(), "thread-1", "按行业分组算年化波动率"))  # type: ignore[arg-type]

    assert agent.call["input"] == {"messages": [{"role": "user", "content": "按行业分组算年化波动率"}]}


async def test_all_three_stream_modes_are_subscribed(recorded: tuple[RecordingAgent, dict[str, Any]]) -> None:
    """少订一个模式就少一类事件：token 在 messages，工具调用在 updates。"""
    agent, _ = recorded
    runner = create_runner(model=DummyModel(), checkpointer=InMemorySaver())

    await drain(runner(FakeBackend(), "thread-1", "一"))  # type: ignore[arg-type]

    assert agent.call["stream_mode"] == STREAM_MODE
    assert set(STREAM_MODE) == {"updates", "messages", "custom"}


async def test_subgraphs_are_streamed_so_the_namespace_is_available(
    recorded: tuple[RecordingAgent, dict[str, Any]],
) -> None:
    """信封的 path 字段来自 ns，而 ns 只在 subgraphs=True 时才有。"""
    agent, _ = recorded
    runner = create_runner(model=DummyModel(), checkpointer=InMemorySaver())

    await drain(runner(FakeBackend(), "thread-1", "一"))  # type: ignore[arg-type]

    assert agent.call["subgraphs"] is True


async def test_a_recursion_limit_bounds_a_runaway_agent(recorded: tuple[RecordingAgent, dict[str, Any]]) -> None:
    agent, _ = recorded
    runner = create_runner(model=DummyModel(), checkpointer=InMemorySaver())

    await drain(runner(FakeBackend(), "thread-1", "一"))  # type: ignore[arg-type]

    assert agent.call["config"]["recursion_limit"] == RECURSION_LIMIT


async def test_the_checkpointer_is_shared_across_runs(recorded: tuple[RecordingAgent, dict[str, Any]]) -> None:
    """会话历史靠它续上，每个 run 换一个的话追问就失忆了。"""
    _, built = recorded
    checkpointer = InMemorySaver()
    runner = create_runner(model=DummyModel(), checkpointer=checkpointer)

    await drain(runner(FakeBackend(), "thread-1", "一"))  # type: ignore[arg-type]
    first = built["checkpointer"]
    await drain(runner(FakeBackend(), "thread-1", "二"))  # type: ignore[arg-type]

    assert first is checkpointer
    assert built["checkpointer"] is checkpointer


@pytest.fixture
def no_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    """剥掉代理变量。

    开发机上设了 ALL_PROXY=socks://…，而 httpx 不认 socks 方案，ChatDeepSeek 构造时
    会直接报错。这是本机环境问题，测试不该因为跑在谁的机器上而结论不同。
    """
    for name in ("ALL_PROXY", "all_proxy"):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.usefixtures("no_proxy")
def test_the_model_is_built_from_settings() -> None:
    settings = Settings(deepseek_api_key=SecretStr("sk-test"), model_main="deepseek-v4-pro")

    model = create_model(settings)

    assert model.model_name == "deepseek-v4-pro"  # type: ignore[attr-defined]


@pytest.mark.usefixtures("no_proxy")
def test_the_model_is_deterministic() -> None:
    """同一份数据同一个问题该给出同一套算法，分析任务不需要发散。"""
    settings = Settings(deepseek_api_key=SecretStr("sk-test"))

    model = create_model(settings)

    assert model.temperature == 0  # type: ignore[attr-defined]
