"""相邻增量的合并。

**验的是「合并前后前端拼出来的文本一模一样」**，不是「条数变少了」——
条数是收益，等价才是正确性。前端把 token 增量逐个追加进同一段，
因此一条整段与 n 条增量必须渲染成同一个结果。
"""

from src.app.event.model import (
    EventType,
    InterruptAction,
    InterruptData,
    ReasoningData,
    ReasoningEvent,
    RunFinishedData,
    RunFinishedEvent,
    TokenData,
    TokenEvent,
    TokenUsage,
    ToolCallData,
    ToolCallEvent,
)
from src.app.run.log import LoggedEvent
from src.app.run.replay import collapse

RUN = "run-1"


def _token(sequence: int, text: str, path: tuple[str, ...] = ()) -> LoggedEvent:
    return LoggedEvent(
        id=f"{sequence}-0",
        event=TokenEvent(ts=sequence, run_id=RUN, path=path, data=TokenData(text=text)),
    )


def _reasoning(sequence: int, text: str, path: tuple[str, ...] = ()) -> LoggedEvent:
    return LoggedEvent(
        id=f"{sequence}-0",
        event=ReasoningEvent(ts=sequence, run_id=RUN, path=path, data=ReasoningData(text=text)),
    )


def _tool(sequence: int) -> LoggedEvent:
    return LoggedEvent(
        id=f"{sequence}-0",
        event=ToolCallEvent(
            ts=sequence,
            run_id=RUN,
            path=(),
            data=ToolCallData(id="call-1", name="execute", args={}),
        ),
    )


def _finished(sequence: int) -> LoggedEvent:
    return LoggedEvent(
        id=f"{sequence}-0",
        event=RunFinishedEvent(
            ts=sequence,
            run_id=RUN,
            path=(),
            data=RunFinishedData(tokens=TokenUsage()),
        ),
    )


def _text(logged: LoggedEvent) -> str:
    data = logged.event.data
    assert isinstance(data, TokenData | ReasoningData)
    return data.text


def test_adjacent_increments_of_one_kind_become_one_event() -> None:
    collapsed = collapse([_token(1, "沪"), _token(2, "深"), _token(3, "300")])

    assert len(collapsed) == 1
    assert _text(collapsed[0]) == "沪深300"


def test_the_merged_event_keeps_the_last_id_and_timestamp() -> None:
    """位置是「读到这里为止」的游标，取最后一条才不会让调用方重复读到已经拿过的那段。"""
    collapsed = collapse([_token(1, "一"), _token(2, "二"), _token(3, "三")])

    assert collapsed[0].id == "3-0"
    assert collapsed[0].event.ts == 3


def test_thinking_and_answering_never_merge_into_each_other() -> None:
    """两者在模型侧就是两个字段、交替流出，合到一起会让思考和结论渲染成一段。"""
    collapsed = collapse([_token(1, "答"), _reasoning(2, "想"), _token(3, "案")])

    assert [one.event.type for one in collapsed] == [EventType.TOKEN, EventType.REASONING, EventType.TOKEN]
    assert [_text(one) for one in collapsed] == ["答", "想", "案"]


def test_an_interleaved_tool_call_breaks_the_run() -> None:
    """跨过工具调用去合并会让文本前后颠倒 —— 工具之后的那段本该排在它后面。"""
    collapsed = collapse([_token(1, "先"), _tool(2), _token(3, "后")])

    assert [one.event.type for one in collapsed] == [EventType.TOKEN, EventType.TOOL_CALL, EventType.TOKEN]
    assert [_text(one) for one in (collapsed[0], collapsed[2])] == ["先", "后"]


def test_increments_of_different_sub_agents_stay_apart() -> None:
    """`path` 是子 agent 的归属，合并跨 path 的两段等于把两个 agent 的话混成一句。"""
    collapsed = collapse([_token(1, "主"), _token(2, "子", path=("researcher",)), _token(3, "主二")])

    assert [one.event.path for one in collapsed] == [(), ("researcher",), ()]
    assert [_text(one) for one in collapsed] == ["主", "子", "主二"]


def test_events_that_are_not_increments_pass_through_untouched() -> None:
    finished = _finished(2)
    collapsed = collapse([_token(1, "完"), finished])

    assert collapsed[1] == finished


def test_an_empty_run_collapses_to_nothing() -> None:
    assert collapse([]) == []


def test_a_single_increment_is_left_as_it_is() -> None:
    assert collapse([_token(1, "独")]) == [_token(1, "独")]


def test_the_interrupt_payload_survives_collapsing() -> None:
    """审批要按最后一条 `interrupt` 的 actions 校验决策数，压缩不能把它弄丢。"""
    from src.app.event.model import InterruptEvent

    interrupt = LoggedEvent(
        id="2-0",
        event=InterruptEvent(
            ts=2,
            run_id=RUN,
            path=(),
            data=InterruptData(
                actions=[InterruptAction(index=0, tool_name="execute", args={}, allowed_decisions=["accept"])]
            ),
        ),
    )

    collapsed = collapse([_token(1, "问"), interrupt])

    assert collapsed[1] == interrupt
