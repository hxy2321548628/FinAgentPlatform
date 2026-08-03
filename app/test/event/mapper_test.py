import json
import logging
from collections.abc import Iterable, Iterator
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, ToolMessage

from event.mapper import StreamChunk, map_chunk
from event.model import (
    Event,
    EventType,
    ReasoningEvent,
    TokenEvent,
    ToolCallEvent,
    ToolResultEvent,
)

FIXTURE = Path(__file__).parent / "fixture" / "stream_chunk.jsonl"

RUN_ID = "run-under-test"

MESSAGE_CLASS: dict[str, type[BaseMessage]] = {
    "AIMessage": AIMessage,
    "AIMessageChunk": AIMessageChunk,
    "ToolMessage": ToolMessage,
}


def _revive_message(raw: dict[str, object]) -> BaseMessage:
    """把 fixture 里的 JSON 还原成 astream 真实吐出的消息对象。

    映射器消费的是 LangChain 对象而不是字典，测试必须还原到同一形状，
    否则测的就不是生产路径。
    """
    # `type` 由消息类自己钉死，传进去会冲突；`__type__` 是 fixture 自己的标记
    field = {key: value for key, value in raw.items() if key not in ("__type__", "type")}
    return MESSAGE_CLASS[str(raw["__type__"])].model_validate(field)


def _revive_update(update: object) -> object:
    if update is None:
        return None
    if isinstance(update, dict):
        return {"messages": [_revive_message(message) for message in update["messages"]]}
    return update


def _revive_chunk(line: str) -> StreamChunk:
    raw = json.loads(line)
    ns, mode, payload = tuple(raw["ns"]), str(raw["mode"]), raw["payload"]
    if mode == "messages":
        return ns, mode, (_revive_message(payload[0]), payload[1])
    if mode == "updates":
        return ns, mode, {node: _revive_update(update) for node, update in payload.items()}
    return ns, mode, payload


@pytest.fixture(scope="module")
def chunk() -> list[StreamChunk]:
    with FIXTURE.open(encoding="utf-8") as stream:
        return [_revive_chunk(line) for line in stream]


@pytest.fixture(scope="module")
def replay(chunk: list[StreamChunk]) -> list[Event]:
    return [event for one in chunk for event in map_chunk(*one, run_id=RUN_ID)]


def _streamed(chunks: Iterable[StreamChunk]) -> Iterator[tuple[StreamChunk, BaseMessage]]:
    """遍历 messages 模式的 chunk 及其携带的消息。"""
    for one in chunks:
        _, mode, payload = one
        if mode == "messages" and isinstance(payload, tuple):
            message = payload[0]
            assert isinstance(message, BaseMessage)
            yield one, message


def _updated(chunks: Iterable[StreamChunk], node: str) -> Iterator[tuple[StreamChunk, BaseMessage]]:
    """遍历 updates 模式里指定节点的 chunk 及其携带的消息。"""
    for one in chunks:
        _, mode, payload = one
        if mode != "updates" or not isinstance(payload, dict):
            continue
        update = payload.get(node)
        if not isinstance(update, dict):
            continue
        for message in update["messages"]:
            assert isinstance(message, BaseMessage)
            yield one, message


def _first(candidate: Iterable[tuple[StreamChunk, BaseMessage]]) -> tuple[StreamChunk, BaseMessage]:
    """取第一个候选，取不到就让测试失败 —— 静默跳过等于假绿。"""
    for one in candidate:
        return one
    raise AssertionError("fixture 里没有满足条件的 chunk")


def _only(events: list[Event]) -> Event:
    """断言一条 chunk 只映射出一个事件，并把它取出来。"""
    assert len(events) == 1
    return events[0]


def test_full_replay_recognises_every_chunk(chunk: list[StreamChunk], caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="event.mapper"):
        for one in chunk:
            map_chunk(*one, run_id=RUN_ID)

    assert caplog.records == []


def test_full_replay_produces_every_agent_event_type(replay: list[Event]) -> None:
    assert {event.type for event in replay} == {
        EventType.TOKEN,
        EventType.REASONING,
        EventType.TOOL_CALL,
        EventType.TOOL_RESULT,
    }


def test_every_event_carries_the_run_id(replay: list[Event]) -> None:
    assert {event.run_id for event in replay} == {RUN_ID}


def test_ts_never_goes_backwards(replay: list[Event]) -> None:
    timestamp = [event.ts for event in replay]

    assert timestamp == sorted(timestamp)


def test_each_tool_result_follows_its_tool_call(replay: list[Event]) -> None:
    call_at = {e.data.id: i for i, e in enumerate(replay) if isinstance(e, ToolCallEvent)}
    result_at = {e.data.tool_call_id: i for i, e in enumerate(replay) if isinstance(e, ToolResultEvent)}

    assert call_at.keys() == result_at.keys()
    assert all(call_at[call_id] < result_at[call_id] for call_id in call_at)


def test_content_chunk_maps_to_a_token_event(chunk: list[StreamChunk]) -> None:
    source, message = _first((one, m) for one, m in _streamed(chunk) if isinstance(m, AIMessageChunk) and m.text)

    event = _only(map_chunk(*source, run_id=RUN_ID))

    assert isinstance(event, TokenEvent)
    assert event.data.text == str(message.text)


def test_reasoning_chunk_maps_to_a_reasoning_event(chunk: list[StreamChunk]) -> None:
    source, message = _first((one, m) for one, m in _streamed(chunk) if m.additional_kwargs.get("reasoning_content"))

    event = _only(map_chunk(*source, run_id=RUN_ID))

    assert isinstance(event, ReasoningEvent)
    assert event.data.text == message.additional_kwargs["reasoning_content"]


def test_reasoning_text_is_never_merged_into_token_text(chunk: list[StreamChunk], replay: list[Event]) -> None:
    """思考过程与正式答复分别流出，合并会让前端把两者渲染在一起。"""
    streamed = [m for _, m in _streamed(chunk) if isinstance(m, AIMessageChunk)]
    expected_token = "".join(str(m.text) for m in streamed)
    expected_reasoning = "".join(str(m.additional_kwargs.get("reasoning_content", "")) for m in streamed)

    token = "".join(e.data.text for e in replay if isinstance(e, TokenEvent))
    reasoning = "".join(e.data.text for e in replay if isinstance(e, ReasoningEvent))

    assert token == expected_token
    assert reasoning == expected_reasoning
    assert token and reasoning


def test_model_node_maps_to_tool_call_events(chunk: list[StreamChunk]) -> None:
    source, message = _first(
        (one, m) for one, m in _updated(chunk, "model") if isinstance(m, AIMessage) and m.tool_calls
    )
    assert isinstance(message, AIMessage)

    event = _only(map_chunk(*source, run_id=RUN_ID))

    assert isinstance(event, ToolCallEvent)
    assert event.data.id == message.tool_calls[0]["id"]
    assert event.data.name == message.tool_calls[0]["name"]
    assert event.data.args == message.tool_calls[0]["args"]


def test_model_node_without_tool_calls_produces_no_event(chunk: list[StreamChunk]) -> None:
    """收尾那轮的文本已由 messages 模式逐字流过，再映射一次就是整段重复。"""
    source, _ = _first((one, m) for one, m in _updated(chunk, "model") if isinstance(m, AIMessage) and not m.tool_calls)

    assert map_chunk(*source, run_id=RUN_ID) == []


def test_tools_node_maps_to_tool_result_events(chunk: list[StreamChunk]) -> None:
    source, message = _first(_updated(chunk, "tools"))
    assert isinstance(message, ToolMessage)

    event = _only(map_chunk(*source, run_id=RUN_ID))

    assert isinstance(event, ToolResultEvent)
    assert event.data.tool_call_id == message.tool_call_id
    assert event.data.name == message.name
    assert event.data.content == message.content


def test_failed_tool_result_keeps_the_error_status(chunk: list[StreamChunk]) -> None:
    source, _ = _first(
        (one, m) for one, m in _updated(chunk, "tools") if isinstance(m, ToolMessage) and m.status == "error"
    )

    event = _only(map_chunk(*source, run_id=RUN_ID))

    assert isinstance(event, ToolResultEvent)
    assert event.data.status == "error"


def test_tool_result_is_emitted_once_per_call(replay: list[Event]) -> None:
    """同一条 ToolMessage 在 updates 与 messages 两种模式各出现一次，只认 updates 那次。"""
    result_id = [e.data.tool_call_id for e in replay if isinstance(e, ToolResultEvent)]

    assert len(result_id) == len(set(result_id))


def test_tool_message_in_messages_mode_produces_no_event(chunk: list[StreamChunk]) -> None:
    source, _ = _first((one, m) for one, m in _streamed(chunk) if isinstance(m, ToolMessage))

    assert map_chunk(*source, run_id=RUN_ID) == []


def test_tool_call_chunk_produces_no_event(chunk: list[StreamChunk]) -> None:
    """工具参数的逐字流不落事件，完整调用统一取自 updates 的 model 节点。"""
    source, _ = _first(
        (one, m) for one, m in _streamed(chunk) if isinstance(m, AIMessageChunk) and m.tool_call_chunks and not m.text
    )

    assert map_chunk(*source, run_id=RUN_ID) == []


def test_usage_metadata_chunk_produces_no_event(chunk: list[StreamChunk]) -> None:
    source, _ = _first((one, m) for one, m in _streamed(chunk) if isinstance(m, AIMessageChunk) and m.usage_metadata)

    assert map_chunk(*source, run_id=RUN_ID) == []


def test_middleware_node_with_null_payload_produces_no_event(chunk: list[StreamChunk]) -> None:
    source = next(c for c in chunk if c[1] == "updates" and isinstance(c[2], dict) and None in c[2].values())

    assert map_chunk(*source, run_id=RUN_ID) == []


def test_custom_mode_produces_no_event_and_no_warning(caplog: pytest.LogCaptureFixture) -> None:
    """沙箱事件走 custom 通道，排队逻辑尚未实现，此处只确认它不被当成未知形状。"""
    with caplog.at_level(logging.WARNING, logger="event.mapper"):
        events = map_chunk((), "custom", {"position": 3}, run_id=RUN_ID)

    assert events == []
    assert caplog.records == []


def test_unknown_mode_warns_instead_of_raising(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="event.mapper"):
        events = map_chunk((), "values", {"messages": []}, run_id=RUN_ID)

    assert events == []
    assert len(caplog.records) == 1


def test_unknown_update_node_warns_instead_of_raising(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="event.mapper"):
        events = map_chunk((), "updates", {"planner": {"messages": []}}, run_id=RUN_ID)

    assert events == []
    assert len(caplog.records) == 1


@pytest.mark.parametrize(
    ("mode", "payload"),
    [
        ("messages", "载荷不是二元组"),
        ("messages", (HumanMessage(content="x"), {})),
        ("updates", ["载荷不是节点字典"]),
        ("updates", {"model": {"没有 messages 这个键": []}}),
        ("updates", {"model": {"messages": "messages 不是列表"}}),
        ("updates", {"model": {"messages": [HumanMessage(content="x")]}}),
        ("updates", {"tools": {"messages": [HumanMessage(content="x")]}}),
    ],
)
def test_malformed_payload_warns_instead_of_raising(
    mode: str, payload: object, caplog: pytest.LogCaptureFixture
) -> None:
    """DeepAgents 换了结构时，一次分析不该因为看不懂某条 chunk 就整个失败。"""
    with caplog.at_level(logging.WARNING, logger="event.mapper"):
        events = map_chunk((), mode, payload, run_id=RUN_ID)

    assert events == []
    assert len(caplog.records) == 1


def test_path_is_empty_when_the_stream_has_no_subgraph(replay: list[Event]) -> None:
    assert {event.path for event in replay} == {()}


def test_path_strips_the_random_task_id() -> None:
    """剥掉 ns 里的随机 task id —— 那是 LangGraph 的内部标识，透出去前端就耦合了它。"""
    payload: tuple[AIMessageChunk, dict[str, object]] = (AIMessageChunk(content="x"), {})

    event = _only(map_chunk(("research:9d1f0a2b",), "messages", payload, run_id=RUN_ID))

    assert event.path == ("research",)
