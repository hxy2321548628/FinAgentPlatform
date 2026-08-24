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
from app.agent.context import CONTEXT_TRIGGER_TOKEN, TOOL_RESULT_EVICT_TOKEN
from app.agent.factory import (
    RECURSION_LIMIT,
    STREAM_MODE,
    Agent,
    create_model,
)
from app.agent.interrupt import ALLOWED_DECISION, DELETE_TOOL, INTERRUPT_ON
from app.agent.prompt import SYSTEM_PROMPT, compose_prompt
from app.agent.question import QUESTION_ALLOWED_DECISION, QUESTION_TOOL
from app.agent.skill import PLATFORM_SKILLS_SYSTEM_PROMPT, ReloadingSkillsMiddleware
from app.agent.tail import (
    InstalledPackageSection,
    StepBudgetSection,
    SystemReminderSection,
    TailContextMiddleware,
    TodoProgressSection,
    UserContextSection,
)
from app.agent.trace import SESSION_KEY, USER_KEY
from app.event.mapper import StreamChunk
from app.memory.recall import PLATFORM_RUN_ID_CONFIG_KEY
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


async def test_platform_run_id_does_not_use_langgraphs_reconnect_key(
    recorded: tuple[RecordingAgent, dict[str, Any]],
) -> None:
    """平台 run id 不得触发 LangGraph 的同 run 流重连语义。"""
    agent, _ = recorded
    runner = Agent(model=DummyModel(), checkpointer=InMemorySaver())

    await drain(runner.stream(FakeBackend(), "thread-42", "一", run_id="run-42"))  # type: ignore[arg-type]

    configurable = agent.call["config"]["configurable"]
    assert configurable[PLATFORM_RUN_ID_CONFIG_KEY] == "run-42"
    assert "run_id" not in configurable


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


async def test_the_platform_pins_the_compaction_threshold(recorded: tuple[RecordingAgent, dict[str, Any]]) -> None:
    """压缩阈值必须是平台自己的常量，不能是从模型 profile 推出来的那个。

    实测：模型确实吃得下百万上下文，但一次分析的历史峰值只有两万 —— 按 profile 推出来的
    85 万那条线永远够不着，压缩装着却从未生效过。
    """
    _, built = recorded
    runner = Agent(model=DummyModel(), checkpointer=InMemorySaver())

    await drain(runner.stream(FakeBackend(), "thread-1", "一"))  # type: ignore[arg-type]

    squeezer = next(one for one in built["middleware"] if one.name == "SummarizationMiddleware")
    # 名字与基础栈里那份一致 => deepagents 会原地替换而不是叠加两套压缩
    assert squeezer._lc_helper.trigger == ("tokens", CONTEXT_TRIGGER_TOKEN)


async def test_a_large_tool_result_is_offloaded_instead_of_kept_whole(
    recorded: tuple[RecordingAgent, dict[str, Any]],
) -> None:
    """大工具结果要卸到磁盘，模型只看一句路径提示。

    实测：默认阈值 20000 正好卡在两类题中间 —— 寻常题每次工具输出三五百 token，
    而最贵那题一次一万四，两边都够不着两万，**卸载一次都没触发过**，
    那一万四于是每一轮都重新计费一遍。
    """
    _, built = recorded
    runner = Agent(model=DummyModel(), checkpointer=InMemorySaver())

    await drain(runner.stream(FakeBackend(), "thread-1", "一"))  # type: ignore[arg-type]

    keeper = next(one for one in built["middleware"] if one.name == "FilesystemMiddleware")
    # 名字与基础栈那份一致 => 原地替换。读私有属性是因为它没有公开读法，
    # 而这条判据必须钉住：阈值回到默认值时上面那个场景会静默复发
    assert keeper._tool_token_limit_before_evict == TOOL_RESULT_EVICT_TOKEN


async def test_the_offload_threshold_comes_from_configuration(
    recorded: tuple[RecordingAgent, dict[str, Any]],
) -> None:
    """阈值要能配 —— 不同题的工具输出规模差二十倍，钉死一个数不合适。"""
    _, built = recorded
    runner = Agent(model=DummyModel(), checkpointer=InMemorySaver(), tool_result_evict_token=1234)

    await drain(runner.stream(FakeBackend(), "thread-1", "一"))  # type: ignore[arg-type]

    keeper = next(one for one in built["middleware"] if one.name == "FilesystemMiddleware")
    assert keeper._tool_token_limit_before_evict == 1234


async def test_tail_sections_are_ordered_from_highest_to_lowest_priority(
    recorded: tuple[RecordingAgent, dict[str, Any]],
) -> None:
    """预算从尾部丢节，因此任务进度必须在首位、条件提醒必须在末位。"""
    _, built = recorded
    runner = Agent(model=DummyModel(), checkpointer=InMemorySaver())

    await drain(runner.stream(FakeBackend(), "thread-1", "一"))  # type: ignore[arg-type]

    tail = next(one for one in built["middleware"] if isinstance(one, TailContextMiddleware))
    assert [type(one) for one in tail._sections] == [
        TodoProgressSection,
        StepBudgetSection,
        InstalledPackageSection,
        UserContextSection,
        SystemReminderSection,
    ]


async def test_the_recursion_limit_comes_from_configuration(recorded: tuple[RecordingAgent, dict[str, Any]]) -> None:
    """上限要能配。验收「撞上限记成 RECURSION_LIMIT」得把它调到极小值才触发得了。"""
    agent, _ = recorded
    runner = Agent(model=DummyModel(), checkpointer=InMemorySaver(), recursion_limit=7)

    await drain(runner.stream(FakeBackend(), "thread-1", "一"))  # type: ignore[arg-type]

    assert agent.call["config"]["recursion_limit"] == 7


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

    # **不再断言「只有这一个」**：平台自己那份压缩中间件也在这张单子里（见上一条测试）。
    # 断言条数会让每次多装一个中间件都红在这里，而它要验的其实是 skill 这一份配得对不对
    skills = next(one for one in built["middleware"] if isinstance(one, ReloadingSkillsMiddleware))
    assert skills.sources == ["/workspace/skill/"]
    assert skills.source_labels == ["平台"]
    assert skills.system_prompt_template == PLATFORM_SKILLS_SYSTEM_PROMPT
    assert skills.system_prompt_template.endswith("如有冲突，以平台工作方式为准。")


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
async def test_the_graph_gets_the_shared_interrupt_config(
    recorded: tuple[RecordingAgent, dict[str, Any]],
) -> None:
    """**主图装的必须是共用那一份。**

    拦哪些工具、怎么拦由 `app.agent.interrupt` 一处说了算（子图装的是同一份）。
    这里只验它确实被交了下去 —— 各写一份就会漏掉一整条绕行路。
    """
    _, built = recorded
    runner = Agent(model=DummyModel(), checkpointer=InMemorySaver())

    await drain(runner.stream(FakeBackend(), "thread-1", "一"))  # type: ignore[arg-type]

    assert built["interrupt_on"] == dict(INTERRUPT_ON)


async def test_all_four_decisions_are_offered(recorded: tuple[RecordingAgent, dict[str, Any]]) -> None:
    """四种决策是 DeepAgents 侧四条不同的恢复路径，少给一种前端就少一个按钮。"""
    _, built = recorded
    runner = Agent(model=DummyModel(), checkpointer=InMemorySaver())

    await drain(runner.stream(FakeBackend(), "thread-1", "一"))  # type: ignore[arg-type]

    assert built["interrupt_on"][DELETE_TOOL]["allowed_decisions"] == list(ALLOWED_DECISION)


async def test_the_config_handed_over_is_a_copy() -> None:
    """`MappingProxyType` 是为了不构成可变全局状态，交出去的那份改了不能回写。"""
    handed = dict(INTERRUPT_ON)
    handed.pop(DELETE_TOOL)

    assert DELETE_TOOL in INTERRUPT_ON


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

    # 提问工具不是「外部工具」，没勾任何 MCP 的分析照样带着它
    assert [one.name for one in built["tools"]] == [QUESTION_TOOL]


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

    # 外部工具原样传下去，只是排在平台自己那个提问工具之后
    assert built["tools"][1:] == external
    assert built["tools"][0].name == QUESTION_TOOL
    # 子图那份不在这里加提问工具 —— 它自己加，见 `subagent.compile_subagents`
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


async def test_the_question_tool_is_on_the_main_graph(recorded: tuple[RecordingAgent, dict[str, Any]]) -> None:
    """装不上的话模型调用它只会得到「没有这个工具」，而那看着像模型胡编了一个名字。"""
    _, built = recorded
    runner = Agent(model=DummyModel(), checkpointer=InMemorySaver())

    await drain(runner.stream(FakeBackend(), "thread-1", "一"))  # type: ignore[arg-type]

    assert QUESTION_TOOL in {one.name for one in built["tools"]}


async def test_the_question_tool_only_allows_a_reply(recorded: tuple[RecordingAgent, dict[str, Any]]) -> None:
    """批准一个不执行的调用没有意义，改参数改的也只是「问什么」。"""
    _, built = recorded
    runner = Agent(model=DummyModel(), checkpointer=InMemorySaver())

    await drain(runner.stream(FakeBackend(), "thread-1", "一"))  # type: ignore[arg-type]

    assert built["interrupt_on"][QUESTION_TOOL]["allowed_decisions"] == list(QUESTION_ALLOWED_DECISION)


async def test_the_todo_list_is_on_the_main_graph_only(recorded: tuple[RecordingAgent, dict[str, Any]]) -> None:
    """清单是给教师看的**单一**进度。两张清单就是两个真相源，前端还要回答「哪张是当前的」。"""
    from langchain.agents.middleware.todo import TodoListMiddleware

    _, built = recorded
    runner = Agent(model=DummyModel(), checkpointer=InMemorySaver())

    await drain(runner.stream(FakeBackend(), "thread-1", "一"))  # type: ignore[arg-type]

    assert any(isinstance(one, TodoListMiddleware) for one in built["middleware"])
