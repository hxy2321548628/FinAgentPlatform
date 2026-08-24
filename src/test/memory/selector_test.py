"""catalog 选择器的严格解析、降级与计量测试。"""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TypedDict, cast

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig, RunnableLambda
from langgraph.constants import TAG_NOSTREAM
from langgraph.graph import END, START, StateGraph

from app.agent.tail import BLOCK_FOOTER, BLOCK_HEADER
from app.event.model import TokenUsage
from app.memory.model import (
    MemoryCatalogEntry,
    MemoryType,
    SelectionFallback,
    SelectorModelProtocol,
    UsageCallbackProtocol,
)
from app.memory.selector import MemorySelector, SelectionParseError, parse_indices, recent_user_messages

NOW = datetime(2026, 8, 21, tzinfo=UTC)


def an_entry(index: int, *, description: str | None = None) -> MemoryCatalogEntry:
    return MemoryCatalogEntry(
        slug=f"memory-{index}",
        name=f"记忆 {index}",
        description=description or f"第 {index} 条年化波动率口径",
        type=MemoryType.PROJECT,
        updated_at=NOW + timedelta(minutes=index),
    )


class FakeModel:
    def __init__(self, content: str, *, delay_second: float = 0.0) -> None:
        self.content = content
        self.delay_second = delay_second
        self.prompts: list[str] = []
        self.configs: list[RunnableConfig | None] = []

    async def ainvoke(self, prompt: str, config: RunnableConfig | None = None) -> AIMessage:
        self.prompts.append(prompt)
        self.configs.append(config)
        if self.delay_second:
            await asyncio.sleep(self.delay_second)
        return AIMessage(
            content=self.content,
            usage_metadata={
                "input_tokens": 17,
                "output_tokens": 3,
                "total_tokens": 20,
                "input_token_details": {"cache_read": 5},
            },
        )


class UsageRecorder:
    def __init__(self) -> None:
        self.items: list[TokenUsage] = []

    def __call__(self, usage: TokenUsage) -> None:
        self.items.append(usage)


def a_selector(
    model: FakeModel,
    *,
    usage: UsageRecorder | None = None,
    timeout_second: float = 1.0,
) -> MemorySelector:
    return MemorySelector(
        model=cast(SelectorModelProtocol, model),
        usage=cast(UsageCallbackProtocol, usage) if usage is not None else None,
        timeout_second=timeout_second,
    )


def test_recent_messages_keep_only_three_real_user_messages() -> None:
    messages = [
        HumanMessage(content="第一条真实问题"),
        SystemMessage(content="系统文字"),
        HumanMessage(content="第二条真实问题"),
        HumanMessage(content=f"{BLOCK_HEADER}\n已用步数：2\n{BLOCK_FOOTER}"),
        AIMessage(content="助手回复"),
        HumanMessage(content="第三条真实问题"),
        HumanMessage(content="第四条真实问题"),
    ]

    assert recent_user_messages(messages) == (
        "第二条真实问题",
        "第三条真实问题",
        "第四条真实问题",
    )


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        ("not-json", SelectionFallback.INVALID_OUTPUT),
        ("```json\n[0]\n```", SelectionFallback.INVALID_OUTPUT),
        ('{"indices":[0]}', SelectionFallback.INVALID_OUTPUT),
        ('["0"]', SelectionFallback.INVALID_OUTPUT),
        ("[true]", SelectionFallback.INVALID_OUTPUT),
        ("[0,0]", SelectionFallback.DUPLICATE_INDEX),
        ("[2]", SelectionFallback.OUT_OF_RANGE),
        ("[0,1,2,3,4,5]", SelectionFallback.INVALID_OUTPUT),
    ],
)
def test_strict_parser_rejects_invalid_indices(raw: str, reason: SelectionFallback) -> None:
    with pytest.raises(SelectionParseError) as raised:
        parse_indices(raw, catalog_size=2)

    assert raised.value.reason == reason


def test_strict_parser_accepts_a_plain_json_index_array() -> None:
    assert parse_indices("[2,0]", catalog_size=3) == (2, 0)


async def test_selector_sends_only_catalog_and_three_recent_questions() -> None:
    model = FakeModel("[1]")
    selector = a_selector(model)
    messages = [HumanMessage(content=f"旧问题 {index}") for index in range(4)]
    messages.append(HumanMessage(content=f"{BLOCK_HEADER}\n状态\n{BLOCK_FOOTER}"))

    selection = await selector.select([an_entry(0), an_entry(1)], messages)

    assert selection.indices == (1,)
    assert selection.fallback is None
    assert "旧问题 0" not in model.prompts[0]
    assert "旧问题 1" in model.prompts[0]
    assert "旧问题 3" in model.prompts[0]
    assert BLOCK_HEADER not in model.prompts[0]
    assert "memory-0" in model.prompts[0]


async def test_selector_marks_its_model_call_as_not_streamed() -> None:
    model = FakeModel("[0]")

    await a_selector(model).select([an_entry(0)], [HumanMessage(content="波动率")])

    assert model.configs == [{"tags": [TAG_NOSTREAM]}]


class _ProbeState(TypedDict, total=False):
    """最小 LangGraph 探针的状态。"""

    selected: tuple[int, ...]


async def test_selector_output_is_hidden_from_graph_messages_but_selection_is_kept() -> None:
    """辅助模型的 ``[0]`` 不得混进主回答，节点状态仍须拿到选择结果。"""
    selector = MemorySelector(model=cast(SelectorModelProtocol, FakeListChatModel(responses=["[0]"])))

    async def select(_: _ProbeState) -> _ProbeState:
        selection = await selector.select([an_entry(0)], [HumanMessage(content="波动率")])
        return {"selected": selection.indices}

    builder = StateGraph(_ProbeState)
    builder.add_node("select", RunnableLambda(select))
    builder.add_edge(START, "select")
    builder.add_edge("select", END)
    graph = builder.compile()

    chunks = [cast(tuple[str, object], chunk) async for chunk in graph.astream({}, stream_mode=["messages", "updates"])]

    assert [payload for mode, payload in chunks if mode == "messages"] == []
    assert [payload for mode, payload in chunks if mode == "updates"] == [{"select": {"selected": (0,)}}]


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        ("not-json", SelectionFallback.INVALID_OUTPUT),
        ("[0,0]", SelectionFallback.DUPLICATE_INDEX),
        ("[99]", SelectionFallback.OUT_OF_RANGE),
    ],
)
async def test_invalid_model_output_falls_back_to_keyword_matching(
    response: str,
    reason: SelectionFallback,
) -> None:
    model = FakeModel(response)
    selector = a_selector(model)
    catalog = [
        an_entry(0, description="教师的图表配色偏好"),
        an_entry(1, description="年化波动率与回测口径"),
    ]

    selection = await selector.select(catalog, [HumanMessage(content="请继续按年化波动率口径计算")])

    assert selection.indices == (1,)
    assert selection.fallback == reason


async def test_timeout_falls_back_to_keyword_matching() -> None:
    model = FakeModel("[0]", delay_second=0.05)
    selector = a_selector(model, timeout_second=0.001)

    selection = await selector.select(
        [an_entry(0, description="年化波动率口径")],
        [HumanMessage(content="继续年化波动率分析")],
    )

    assert selection.indices == (0,)
    assert selection.fallback == SelectionFallback.TIMEOUT


async def test_keyword_fallback_never_returns_more_than_five_entries() -> None:
    model = FakeModel("invalid")
    selector = a_selector(model)

    selection = await selector.select(
        [an_entry(index, description=f"波动率口径 {index}") for index in range(8)],
        [HumanMessage(content="波动率口径")],
    )

    assert len(selection.indices) == 5
    assert selection.fallback == SelectionFallback.INVALID_OUTPUT


async def test_selector_reports_auxiliary_model_usage() -> None:
    model = FakeModel("[0]")
    usage = UsageRecorder()
    selector = a_selector(model, usage=usage)

    selection = await selector.select([an_entry(0)], [HumanMessage(content="波动率")])

    assert usage.items == [TokenUsage(input_cache_read=5, input_uncached=12, output=3)]
    assert selection.usage == TokenUsage(input_cache_read=5, input_uncached=12, output=3)
    assert selection.duration_ms >= 0


async def test_timeout_keeps_an_auditable_duration_even_without_sdk_usage() -> None:
    selector = a_selector(FakeModel("[0]", delay_second=0.05), timeout_second=0.01)

    selection = await selector.select(
        [an_entry(0, description="波动率")],
        [HumanMessage(content="波动率")],
    )

    assert selection.fallback is SelectionFallback.TIMEOUT
    assert selection.usage == TokenUsage()
    assert selection.duration_ms >= 1
