import pytest
from pydantic import ValidationError

from event.model import (
    EventType,
    ReasoningData,
    ReasoningEvent,
    TokenData,
    TokenEvent,
    ToolCallData,
    ToolCallEvent,
    ToolResultData,
    ToolResultEvent,
)


# 这些字面值是前后端唯一共用的契约，前端 Zod schema 直接照抄。
# 改一个字符就是破坏前端，因此逐个钉死而不是遍历枚举。
def test_event_type_values_match_the_contract() -> None:
    assert EventType.RUN_STARTED.value == "run.started"
    assert EventType.RUN_FINISHED.value == "run.finished"
    assert EventType.RUN_FAILED.value == "run.failed"
    assert EventType.RUN_CANCELLED.value == "run.cancelled"
    assert EventType.SANDBOX_QUEUED.value == "sandbox.queued"
    assert EventType.SANDBOX_READY.value == "sandbox.ready"
    assert EventType.ERROR.value == "error"
    assert EventType.TOKEN.value == "token"
    assert EventType.REASONING.value == "reasoning"
    assert EventType.TOOL_CALL.value == "tool_call"
    assert EventType.TOOL_RESULT.value == "tool_result"
    assert EventType.TODO_UPDATED.value == "todo.updated"
    assert EventType.SUBAGENT_STARTED.value == "subagent.started"
    assert EventType.SUBAGENT_FINISHED.value == "subagent.finished"
    assert EventType.INTERRUPT.value == "interrupt"


def test_event_serializes_to_the_contract_envelope() -> None:
    event = TokenEvent(ts=1753948800123, run_id="8f3a", path=(), data=TokenData(text="好的"))

    dumped = event.model_dump(mode="json")

    assert dumped == {
        "type": "token",
        "ts": 1753948800123,
        "run_id": "8f3a",
        "path": [],
        "data": {"text": "好的"},
    }


def test_subagent_path_serializes_as_a_json_array() -> None:
    event = TokenEvent(ts=1, run_id="r", path=("research",), data=TokenData(text="x"))

    assert event.model_dump(mode="json")["path"] == ["research"]


def test_blank_token_text_is_rejected() -> None:
    with pytest.raises(ValidationError):
        TokenData(text="")


def test_blank_reasoning_text_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ReasoningData(text="")


def test_reasoning_event_is_a_distinct_type_from_token() -> None:
    reasoning = ReasoningEvent(ts=1, run_id="r", path=(), data=ReasoningData(text="The"))

    assert reasoning.type == EventType.REASONING


def test_tool_call_args_accept_the_shape_the_model_produced() -> None:
    data = ToolCallData(id="call_00", name="execute", args={"command": "python x.py", "timeout": 30})

    assert data.args == {"command": "python x.py", "timeout": 30}


def test_tool_call_without_args_is_valid() -> None:
    data = ToolCallData(id="call_00", name="ls", args={})

    assert data.args == {}


def test_tool_result_keeps_the_error_status() -> None:
    event = ToolResultEvent(
        ts=1,
        run_id="r",
        path=(),
        data=ToolResultData(
            tool_call_id="call_00",
            name="read_file",
            content="Error: File '/workspace/missing.csv': file_not_found",
            status="error",
        ),
    )

    assert event.data.status == "error"


def test_tool_result_rejects_a_status_outside_the_contract() -> None:
    with pytest.raises(ValidationError):
        ToolResultData(tool_call_id="c", name="execute", content="", status="pending")


def test_tool_call_event_type_is_fixed_by_the_class() -> None:
    event = ToolCallEvent(ts=1, run_id="r", path=(), data=ToolCallData(id="c", name="ls", args={}))

    assert event.type == EventType.TOOL_CALL
