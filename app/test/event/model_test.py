import pytest
from pydantic import ValidationError

from event.model import (
    TERMINAL_EVENT_TYPE,
    ErrorData,
    EventType,
    ReasoningData,
    ReasoningEvent,
    RunErrorCode,
    RunFailedData,
    RunFailedEvent,
    RunFinishedData,
    RunFinishedEvent,
    RunStartedData,
    RunStartedEvent,
    RunStatus,
    SandboxQueuedData,
    SandboxQueuedEvent,
    SandboxReadyData,
    SandboxReadyEvent,
    TokenData,
    TokenEvent,
    TokenUsage,
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


# ------------------------------------------------------------------ 平台层事件
def test_run_status_values_match_the_contract() -> None:
    assert RunStatus.QUEUED.value == "queued"
    assert RunStatus.RUNNING.value == "running"
    assert RunStatus.SUCCEEDED.value == "succeeded"
    assert RunStatus.FAILED.value == "failed"


def test_run_started_serializes_to_the_contract_envelope() -> None:
    event = RunStartedEvent(ts=1, run_id="r", path=(), data=RunStartedData(thread_id="t"))

    assert event.model_dump(mode="json") == {
        "type": "run.started",
        "ts": 1,
        "run_id": "r",
        "path": [],
        # `resumed` 是 P3 加的：一次 run 会多次入队，每轮审批之后都重新投递，
        # 因此这个事件不再等于「第一次开跑」。契约只增字段，不改已有字段的语义
        "data": {"thread_id": "t", "resumed": False},
    }


def test_run_finished_splits_the_token_usage_by_cache_hit() -> None:
    """§6.4 的配额要按未命中部分加权算，给一个总数等于让前端自己去猜怎么拆。"""
    event = RunFinishedEvent(
        ts=1,
        run_id="r",
        path=(),
        data=RunFinishedData(tokens=TokenUsage(input_cache_read=189312, input_uncached=115328, output=8701)),
    )

    assert event.model_dump(mode="json")["data"] == {
        "status": "succeeded",
        "tokens": {"input_cache_read": 189312, "input_uncached": 115328, "output": 8701},
        "artifacts": [],
    }


def test_token_usage_adds_up_across_model_calls() -> None:
    """一次 run 有十几次模型调用，用量是逐次累加出来的。"""
    total = TokenUsage(input_cache_read=1, input_uncached=2, output=3) + TokenUsage(
        input_cache_read=10, input_uncached=20, output=30
    )

    assert total == TokenUsage(input_cache_read=11, input_uncached=22, output=33)


def test_token_usage_defaults_to_zero() -> None:
    assert TokenUsage() == TokenUsage(input_cache_read=0, input_uncached=0, output=0)


def test_run_finished_carries_the_artifact_ids() -> None:
    """前端拿这些标识拼产物下载的 URL。"""
    event = RunFinishedEvent(
        ts=1,
        run_id="r",
        path=(),
        data=RunFinishedData(artifacts=["8f3a/industry_volatility.png"]),
    )

    assert event.model_dump(mode="json")["data"]["artifacts"] == ["8f3a/industry_volatility.png"]


def test_run_failed_tells_the_frontend_whether_retrying_is_worth_it() -> None:
    event = RunFailedEvent(
        ts=1,
        run_id="r",
        path=(),
        data=RunFailedData(code=RunErrorCode.SANDBOX_QUEUE_TIMEOUT, message="等待沙箱超过 600 秒", retryable=True),
    )

    assert event.model_dump(mode="json")["data"] == {
        "code": "SANDBOX_QUEUE_TIMEOUT",
        "message": "等待沙箱超过 600 秒",
        "retryable": True,
    }


def test_sandbox_queued_reports_the_position() -> None:
    event = SandboxQueuedEvent(ts=1, run_id="r", path=(), data=SandboxQueuedData(position=3))

    assert event.model_dump(mode="json")["data"] == {"position": 3}


def test_a_position_of_zero_is_rejected() -> None:
    """排位从 1 起算，0 会让前端显示「前面还有 0 个」。"""
    with pytest.raises(ValidationError):
        SandboxQueuedData(position=0)


def test_sandbox_ready_carries_an_empty_object() -> None:
    """信封形状保持一致，前端不必为这一种事件写特例。"""
    event = SandboxReadyEvent(ts=1, run_id="r", path=(), data=SandboxReadyData())

    assert event.model_dump(mode="json")["data"] == {}


def test_error_does_not_terminate_the_run() -> None:
    """与 run.failed 的区别就是这个：前者是终态，后者只是过程中的告警。"""
    event = ErrorData(code=RunErrorCode.INTERNAL, message="工具调用失败，已让模型重试")

    assert EventType.ERROR not in TERMINAL_EVENT_TYPE
    assert event.message


def test_terminal_types_cover_every_way_a_run_can_end() -> None:
    """漏一种，订阅那个 run 的 SSE 连接就永远等不到收尾。"""
    assert {EventType.RUN_FINISHED, EventType.RUN_FAILED, EventType.RUN_CANCELLED} == TERMINAL_EVENT_TYPE
