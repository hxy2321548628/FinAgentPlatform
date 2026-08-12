"""决策校验与重排的测试。

**缺失或重复的 index 必须被拒**：静默地少一个决策，恢复时就会把 A 的决策套到
B 的调用上 —— 而那种错不报错，只是 agent 做了一件教师没批准的事。
"""

import pytest

from run.decision import Decision, DecisionError, DecisionType, EditedAction, check, to_resume


def _decision(index: int, kind: DecisionType = DecisionType.APPROVE, **extra: object) -> Decision:
    return Decision(index=index, type=kind, **extra)


def test_a_full_set_of_decisions_passes() -> None:
    check([_decision(0), _decision(1)], expected=2)


def test_a_missing_index_is_refused() -> None:
    with pytest.raises(DecisionError):
        check([_decision(0)], expected=2)


def test_a_duplicated_index_is_refused() -> None:
    with pytest.raises(DecisionError):
        check([_decision(0), _decision(0)], expected=2)


def test_an_out_of_range_index_is_refused() -> None:
    with pytest.raises(DecisionError):
        check([_decision(0), _decision(7)], expected=2)


def test_too_many_decisions_are_refused() -> None:
    with pytest.raises(DecisionError):
        check([_decision(0), _decision(1), _decision(2)], expected=2)


def test_deciding_when_nothing_is_pending_is_refused() -> None:
    with pytest.raises(DecisionError):
        check([_decision(0)], expected=0)


def test_an_edit_without_the_edited_action_is_refused() -> None:
    """`edit` 说的是「改成这样再执行」，不给改成什么就没法执行。"""
    with pytest.raises(DecisionError):
        check([_decision(0, DecisionType.EDIT)], expected=1)


def test_decisions_are_reordered_by_index() -> None:
    """DeepAgents 要求决策顺序与 `action_requests` 严格对齐，重排在平台这一侧做。"""
    resumed = to_resume([_decision(1, DecisionType.REJECT, message="乙"), _decision(0)])

    assert [one["type"] for one in resumed] == ["approve", "reject"]


def test_a_rejection_carries_its_message() -> None:
    resumed = to_resume([_decision(0, DecisionType.REJECT, message="这段代码会删掉原始数据")])

    assert resumed == [{"type": "reject", "message": "这段代码会删掉原始数据"}]


def test_a_response_carries_its_message() -> None:
    """`respond` 不执行工具，人的回答直接当成工具结果。"""
    resumed = to_resume([_decision(0, DecisionType.RESPOND, message="直接用去年的口径即可")])

    assert resumed == [{"type": "respond", "message": "直接用去年的口径即可"}]


def test_an_edit_carries_the_edited_action() -> None:
    resumed = to_resume(
        [
            Decision(
                index=0,
                type=DecisionType.EDIT,
                edited_action=EditedAction(name="delete", args={"file_path": "/workspace/outputs/tmp.csv"}),
            )
        ]
    )

    assert resumed == [
        {"type": "edit", "edited_action": {"name": "delete", "args": {"file_path": "/workspace/outputs/tmp.csv"}}}
    ]


def test_an_approval_carries_nothing_else() -> None:
    """多塞一个字段可能让框架按别的分支走，approve 就是照原样执行。"""
    assert to_resume([_decision(0)]) == [{"type": "approve"}]
