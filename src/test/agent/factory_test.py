"""智能体装配的测试。

这里只验装配参数是否按设计传下去，不跑真实模型 —— CI 里没有凭据，也不该花钱。
"""

from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import pytest
from deepagents.backends.protocol import BackendProtocol
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import SecretStr

from app.agent.config import AgentConfig
from app.agent.factory import (
    ALLOWED_DECISION,
    DELETE_TOOL,
    INTERRUPT_ON,
    RECURSION_LIMIT,
    STREAM_MODE,
    Agent,
    create_model,
)
from app.agent.prompt import SYSTEM_PROMPT, compose_prompt
from app.agent.skill import PLATFORM_SKILLS_SYSTEM_PROMPT, ReloadingSkillsMiddleware
from app.agent.trace import SESSION_KEY, USER_KEY
from app.event.mapper import StreamChunk
from config import Settings


class RecordingAgent:
    """记录 astream 收到了什么的假图。"""

    def __init__(self) -> None:
        self.call: dict[str, Any] = {}
        self.interrupts: tuple[Any, ...] = ()

    async def aget_state(self, config: dict[str, object]) -> Any:  # noqa: ANN401 - 替身照单全收
        return SimpleNamespace(interrupts=self.interrupts)

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

    monkeypatch.setattr("app.agent.factory.create_deep_agent", fake_create_deep_agent)
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
    runner = Agent(model=DummyModel(), checkpointer=InMemorySaver())

    await drain(runner.stream(FakeBackend(), "thread-1", "算个波动率"))  # type: ignore[arg-type]

    assert built["system_prompt"] == SYSTEM_PROMPT


async def test_a_run_config_reaches_the_graph_prompt(recorded: tuple[RecordingAgent, dict[str, Any]]) -> None:
    _, built = recorded
    runner = Agent(model=DummyModel(), checkpointer=InMemorySaver())
    config = AgentConfig(system_prompt="每一句都以「喵」开头。")

    await drain(runner.stream(FakeBackend(), "thread-1", "一", config))  # type: ignore[arg-type]

    assert built["system_prompt"] == compose_prompt(config)


async def test_the_sandbox_backend_drives_the_builtin_tools(recorded: tuple[RecordingAgent, dict[str, Any]]) -> None:
    """本期不自定义工具，只换驱动内置工具的后端 —— 传错这个参数文件就落进 LangGraph state 了。"""
    _, built = recorded
    backend: BackendProtocol = FakeBackend()  # type: ignore[assignment]
    runner = Agent(model=DummyModel(), checkpointer=InMemorySaver())

    await drain(runner.stream(backend, "thread-1", "一"))

    assert built["backend"] is backend


async def test_the_thread_id_isolates_conversation_history(
    recorded: tuple[RecordingAgent, dict[str, Any]],
) -> None:
    agent, _ = recorded
    runner = Agent(model=DummyModel(), checkpointer=InMemorySaver())

    await drain(runner.stream(FakeBackend(), "thread-42", "一"))  # type: ignore[arg-type]

    assert agent.call["config"]["configurable"]["thread_id"] == "thread-42"


async def test_a_configured_callback_reaches_the_graph_with_the_identity(
    recorded: tuple[RecordingAgent, dict[str, Any]],
) -> None:
    """回调与身份要一起进 config。

    **这一环断了不会报错**：图照常跑完、分析照常出结果，只是 Langfuse 那边什么都没有，
    或者有 trace 但每条都没有主人。
    """
    agent, _ = recorded
    handler = BaseCallbackHandler()
    runner = Agent(model=DummyModel(), checkpointer=InMemorySaver(), callback=handler)

    await drain(runner.stream(FakeBackend(), "thread-1", "一", user_id="teacher-1"))  # type: ignore[arg-type]

    config = agent.call["config"]
    assert config["callbacks"] == [handler]
    assert config["metadata"] == {SESSION_KEY: "thread-1", USER_KEY: "teacher-1"}


async def test_without_a_callback_the_config_stays_clean(recorded: tuple[RecordingAgent, dict[str, Any]]) -> None:
    """没配 Langfuse 时连 metadata 都不放 —— 那几个键对 LangGraph 毫无意义。"""
    agent, _ = recorded
    runner = Agent(model=DummyModel(), checkpointer=InMemorySaver())

    await drain(runner.stream(FakeBackend(), "thread-1", "一", user_id="teacher-1"))  # type: ignore[arg-type]

    assert "callbacks" not in agent.call["config"]
    assert "metadata" not in agent.call["config"]


async def test_the_question_is_sent_as_a_user_message(recorded: tuple[RecordingAgent, dict[str, Any]]) -> None:
    agent, _ = recorded
    runner = Agent(model=DummyModel(), checkpointer=InMemorySaver())

    await drain(runner.stream(FakeBackend(), "thread-1", "按行业分组算年化波动率"))  # type: ignore[arg-type]

    assert agent.call["input"] == {"messages": [{"role": "user", "content": "按行业分组算年化波动率"}]}


async def test_all_three_stream_modes_are_subscribed(recorded: tuple[RecordingAgent, dict[str, Any]]) -> None:
    """少订一个模式就少一类事件：token 在 messages，工具调用在 updates。"""
    agent, _ = recorded
    runner = Agent(model=DummyModel(), checkpointer=InMemorySaver())

    await drain(runner.stream(FakeBackend(), "thread-1", "一"))  # type: ignore[arg-type]

    assert agent.call["stream_mode"] == STREAM_MODE
    assert set(STREAM_MODE) == {"updates", "messages", "custom"}


async def test_subgraphs_are_streamed_so_the_namespace_is_available(
    recorded: tuple[RecordingAgent, dict[str, Any]],
) -> None:
    """信封的 path 字段来自 ns，而 ns 只在 subgraphs=True 时才有。"""
    agent, _ = recorded
    runner = Agent(model=DummyModel(), checkpointer=InMemorySaver())

    await drain(runner.stream(FakeBackend(), "thread-1", "一"))  # type: ignore[arg-type]

    assert agent.call["subgraphs"] is True


async def test_a_recursion_limit_bounds_a_runaway_agent(recorded: tuple[RecordingAgent, dict[str, Any]]) -> None:
    agent, _ = recorded
    runner = Agent(model=DummyModel(), checkpointer=InMemorySaver())

    await drain(runner.stream(FakeBackend(), "thread-1", "一"))  # type: ignore[arg-type]

    assert agent.call["config"]["recursion_limit"] == RECURSION_LIMIT


async def test_the_checkpointer_is_shared_across_runs(recorded: tuple[RecordingAgent, dict[str, Any]]) -> None:
    """会话历史靠它续上，每个 run 换一个的话追问就失忆了。"""
    _, built = recorded
    checkpointer = InMemorySaver()
    runner = Agent(model=DummyModel(), checkpointer=checkpointer)

    await drain(runner.stream(FakeBackend(), "thread-1", "一"))  # type: ignore[arg-type]
    first = built["checkpointer"]
    await drain(runner.stream(FakeBackend(), "thread-1", "二"))  # type: ignore[arg-type]

    assert first is checkpointer
    assert built["checkpointer"] is checkpointer


async def test_platform_skills_are_loaded_by_the_reloading_middleware(
    recorded: tuple[RecordingAgent, dict[str, Any]],
) -> None:
    _, built = recorded
    runner = Agent(model=DummyModel(), checkpointer=InMemorySaver())

    await drain(runner.stream(FakeBackend(), "thread-1", "一"))  # type: ignore[arg-type]

    middleware = built["middleware"]
    assert len(middleware) == 1
    assert isinstance(middleware[0], ReloadingSkillsMiddleware)
    assert middleware[0].sources == ["/workspace/skill/"]
    assert middleware[0].source_labels == ["平台"]
    assert middleware[0].system_prompt_template == PLATFORM_SKILLS_SYSTEM_PROMPT
    assert middleware[0].system_prompt_template.endswith("如有冲突，以平台工作方式为准。")


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


# ------------------------------------------------------------------ HITL
async def test_only_delete_is_intercepted(recorded: tuple[RecordingAgent, dict[str, Any]]) -> None:
    """**只全量拦 `delete`**。

    P0 实测一次分析里 agent 调了 16 次工具、`delete` 一次都没调 —— 低频高危，
    全量拦不伤可用性。给 `execute` 全量加审批则要教师点十几次确认，平台会变得没法用。
    """
    _, built = recorded
    runner = Agent(model=DummyModel(), checkpointer=InMemorySaver())

    await drain(runner.stream(FakeBackend(), "thread-1", "一"))  # type: ignore[arg-type]

    assert set(built["interrupt_on"]) == {DELETE_TOOL}


async def test_all_four_decisions_are_offered(recorded: tuple[RecordingAgent, dict[str, Any]]) -> None:
    """四种决策是 DeepAgents 侧四条不同的恢复路径，少给一种前端就少一个按钮。"""
    _, built = recorded
    runner = Agent(model=DummyModel(), checkpointer=InMemorySaver())

    await drain(runner.stream(FakeBackend(), "thread-1", "一"))  # type: ignore[arg-type]

    assert built["interrupt_on"][DELETE_TOOL]["allowed_decisions"] == list(ALLOWED_DECISION)


async def test_no_when_predicate_is_configured() -> None:
    """本期不写任何 `when`：非确定性谓词会破坏基于索引的匹配，而它坏掉的方式是静默的。"""
    for config in INTERRUPT_ON.values():
        assert "when" not in config


async def test_resuming_carries_the_decisions(recorded: tuple[RecordingAgent, dict[str, Any]]) -> None:
    agent, _ = recorded
    runner = Agent(model=DummyModel(), checkpointer=InMemorySaver())

    await drain(runner.resume(FakeBackend(), "thread-1", [{"type": "approve"}]))  # type: ignore[arg-type]

    assert agent.call["input"].resume == {"decisions": [{"type": "approve"}]}


async def test_resuming_keeps_the_same_run_prompt(recorded: tuple[RecordingAgent, dict[str, Any]]) -> None:
    _, built = recorded
    runner = Agent(model=DummyModel(), checkpointer=InMemorySaver())
    config = AgentConfig(system_prompt="一次 run 内不能换提示词。")

    await drain(runner.resume(FakeBackend(), "thread-1", [{"type": "approve"}], config))  # type: ignore[arg-type]

    assert built["system_prompt"] == compose_prompt(config)


async def test_a_thread_without_an_interrupt_has_nothing_pending(
    recorded: tuple[RecordingAgent, dict[str, Any]],
) -> None:
    runner = Agent(model=DummyModel(), checkpointer=InMemorySaver())

    assert await runner.pending(FakeBackend(), "thread-1") == []  # type: ignore[arg-type]


async def test_pending_state_is_read_from_the_same_configured_graph(
    recorded: tuple[RecordingAgent, dict[str, Any]],
) -> None:
    _, built = recorded
    runner = Agent(model=DummyModel(), checkpointer=InMemorySaver())
    config = AgentConfig(system_prompt="查中断也不能换图。")

    await runner.pending(FakeBackend(), "thread-1", config)  # type: ignore[arg-type]

    assert built["system_prompt"] == compose_prompt(config)


async def test_two_parallel_arrays_are_merged_into_one_indexed_list(
    recorded: tuple[RecordingAgent, dict[str, Any]],
) -> None:
    """两个平行数组合并成一个带 index 的列表。

    DeepAgents 给的是 `action_requests` 与 `review_configs` —— 前端不该被迫
    自己对齐两个数组的下标。
    """
    agent, _ = recorded
    agent.interrupts = (
        SimpleNamespace(
            value={
                "action_requests": [
                    {"name": "delete", "args": {"file_path": "/workspace/data.csv"}},
                    {"name": "delete", "args": {"file_path": "/workspace/old.csv"}},
                ],
                "review_configs": [{"action_name": "delete", "allowed_decisions": ["approve", "reject"]}],
            }
        ),
    )
    runner = Agent(model=DummyModel(), checkpointer=InMemorySaver())

    actions = await runner.pending(FakeBackend(), "thread-1")  # type: ignore[arg-type]

    assert [one.index for one in actions] == [0, 1]
    assert [one.tool_name for one in actions] == ["delete", "delete"]
    assert actions[0].args == {"file_path": "/workspace/data.csv"}
    assert actions[0].allowed_decisions == ["approve", "reject"]


async def test_an_unreadable_interrupt_is_treated_as_none(recorded: tuple[RecordingAgent, dict[str, Any]]) -> None:
    """读不懂一个中断不该把整次分析掀掉 —— 宁可让它正常跑完。"""
    agent, _ = recorded
    agent.interrupts = (SimpleNamespace(value="这不是我认识的形状"),)
    runner = Agent(model=DummyModel(), checkpointer=InMemorySaver())

    assert await runner.pending(FakeBackend(), "thread-1") == []  # type: ignore[arg-type]


async def test_an_empty_subagent_snapshot_does_not_touch_the_loader(
    recorded: tuple[RecordingAgent, dict[str, Any]],
) -> None:
    class Loader:
        async def load_subagent(self, agent_id: str, version: int) -> None:
            raise AssertionError("空快照不应访问子智能体仓储")

    _, built = recorded
    runner = Agent(model=DummyModel(), checkpointer=InMemorySaver(), subagent_loader=Loader())

    await drain(runner.stream(FakeBackend(), "thread-1", "一", AgentConfig()))  # type: ignore[arg-type]

    assert built["subagents"] is None


async def test_a_compiled_subagent_list_reaches_deepagents(
    recorded: tuple[RecordingAgent, dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.agent.config import SubagentReference

    expected: list[Any] = [{"name": "volatility-expert"}]

    async def fake_compile(*argument: Any, **keyword: Any) -> list[Any]:  # noqa: ANN401 - 替身照单全收
        return expected

    monkeypatch.setattr("app.agent.factory.compile_subagents", fake_compile)
    _, built = recorded
    runner = Agent(model=DummyModel(), checkpointer=InMemorySaver(), subagent_loader=object())  # type: ignore[arg-type]
    config = AgentConfig(subagents=[SubagentReference(agent_id="agent-1", version=1, name="volatility-expert")])

    await drain(runner.stream(FakeBackend(), "thread-1", "一", config))  # type: ignore[arg-type]

    assert built["subagents"] is expected


async def test_an_empty_mcp_snapshot_does_not_touch_the_catalog(
    recorded: tuple[RecordingAgent, dict[str, Any]],
) -> None:
    """不挂 MCP 的 run 一个额外动作都不做 —— 绝大多数分析走的是这条路。

    症状会是「平台好像变慢了」，而没有任何日志指向多出来的那次外网往返。
    """

    class Loader:
        async def load_mcp_target(self, server_id: str) -> None:
            raise AssertionError("空快照不应访问 MCP 目录")

    _, built = recorded
    runner = Agent(model=DummyModel(), checkpointer=InMemorySaver(), mcp_loader=Loader())

    await drain(runner.stream(FakeBackend(), "thread-1", "一", AgentConfig()))  # type: ignore[arg-type]

    assert built["tools"] == []


async def test_external_tools_reach_both_the_main_graph_and_the_subagents(
    recorded: tuple[RecordingAgent, dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """一次分析勾了哪些外部服务是 run 的属性，不是某一层 agent 的属性。"""
    from app.agent.config import McpReference, SubagentReference

    external: list[Any] = [SimpleNamespace(name="search_paper")]
    handed: dict[str, Any] = {}

    async def fake_load(*argument: Any, **keyword: Any) -> list[Any]:  # noqa: ANN401 - 替身照单全收
        return external

    async def fake_compile(*argument: Any, **keyword: Any) -> list[Any]:  # noqa: ANN401 - 替身照单全收
        handed.update(keyword)
        return [{"name": "volatility-expert"}]

    monkeypatch.setattr("app.agent.factory.load_mcp_tools", fake_load)
    monkeypatch.setattr("app.agent.factory.compile_subagents", fake_compile)
    _, built = recorded
    runner = Agent(
        model=DummyModel(),
        checkpointer=InMemorySaver(),
        subagent_loader=object(),  # type: ignore[arg-type]
        mcp_loader=object(),  # type: ignore[arg-type]
    )
    config = AgentConfig(
        mcps=[McpReference(server_id="srv-1", name="paper-search")],
        subagents=[SubagentReference(agent_id="agent-1", version=1, name="volatility-expert")],
    )

    await drain(runner.stream(FakeBackend(), "thread-1", "一", config))  # type: ignore[arg-type]

    assert built["tools"] is external
    assert handed["tools"] is external


async def test_an_mcp_snapshot_without_a_catalog_fails_loudly(
    recorded: tuple[RecordingAgent, dict[str, Any]],
) -> None:
    """静默跑成「没挂 MCP」的话，教师看到的是「我明明勾了，怎么没用上」。"""
    from app.agent.config import McpReference

    runner = Agent(model=DummyModel(), checkpointer=InMemorySaver())
    config = AgentConfig(mcps=[McpReference(server_id="srv-1", name="paper-search")])

    with pytest.raises(RuntimeError, match="MCP"):
        await drain(runner.stream(FakeBackend(), "thread-1", "一", config))  # type: ignore[arg-type]


async def test_asking_whether_anything_is_pending_does_not_reach_out_to_the_network(
    recorded: tuple[RecordingAgent, dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """查中断不该再连一遍那台校外机器。

    中断记在 checkpoint 里，读它与图上绑了哪些工具无关；而每条 run 流跑完都要查一次
    中断 —— 不去掉的话，挂了 MCP 的分析每次都连两遍（实测日志里两条装配相隔 8 秒），
    而每一次都可能失败、都会记进熔断计数。
    """
    from app.agent.config import McpReference

    loaded = 0

    async def counting_load(*argument: Any, **keyword: Any) -> list[Any]:  # noqa: ANN401 - 替身照单全收
        nonlocal loaded
        loaded += 1
        return []

    monkeypatch.setattr("app.agent.factory.load_mcp_tools", counting_load)
    runner = Agent(model=DummyModel(), checkpointer=InMemorySaver(), mcp_loader=object())  # type: ignore[arg-type]
    config = AgentConfig(mcps=[McpReference(server_id="srv-1", name="paper-search")])

    await drain(runner.stream(FakeBackend(), "thread-1", "一", config))  # type: ignore[arg-type]
    assert loaded == 1

    await runner.pending(FakeBackend(), "thread-1", config)  # type: ignore[arg-type]

    assert loaded == 1
