"""教师的决策：形状与校验。

**用显式 `index`，不依赖数组顺序。** DeepAgents 的 `Command(resume=…)` 要求决策顺序
与 `action_requests` 严格对齐，但把这个约束透给前端是个迟早出错的契约 ——
由这里按 `index` 重排。缺失或重复的 index 一律拒绝：静默地少一个决策，
恢复时就会把 A 的决策套到 B 的调用上，而那种错不报错。

**四种决策是 DeepAgents 侧四条不同的恢复路径**，只验 `approve` 等于没验。
`edit` 与 `respond` 各有一个必填项：前者缺了没法执行，后者缺了库里那支直接
`decision["message"]` 抛 KeyError —— 而那时决策早已被接受、run 已经重投，
炸在恢复那一刻，报错一个字都不指向「少了一句话」。

**这个模块是叶子**：只依赖 pydantic。决策要随任务消息走，而任务消息的定义被配置层
引用 —— 把这些形状放进带数据库依赖的模块里会兜出一个循环。
"""

from enum import StrEnum

from pydantic import BaseModel, Field


class DecisionType(StrEnum):
    """教师能做的四种决策。"""

    APPROVE = "approve"
    REJECT = "reject"
    EDIT = "edit"
    RESPOND = "respond"


class EditedAction(BaseModel):
    """改过参数之后要执行的调用。"""

    name: str = Field(min_length=1, description="工具名")
    args: dict[str, object] = Field(default_factory=dict, description="改过的参数")


class Decision(BaseModel):
    """对一次待确认调用的答复。"""

    index: int = Field(ge=0, description="对应 interrupt 事件里 actions 的下标")
    type: DecisionType = Field(description="决策类型")
    message: str | None = Field(default=None, description="reject 与 respond 回给 agent 的话")
    edited_action: EditedAction | None = Field(default=None, description="edit 时改成什么")


class DecisionError(ValueError):
    """决策数组与待确认的调用对不上。"""


def check(decisions: list[Decision], *, expected: int) -> None:
    """校验决策数组能一一对上待确认的调用。

    Args:
        decisions: 教师给的决策。
        expected: 这次中断里待确认的调用数。

    Raises:
        DecisionError: 数量不符、index 重复、有 index 缺失，或 edit / respond 缺了各自的必填项。
    """
    if expected == 0:
        message = "这个 run 现在没有待确认的调用"
        raise DecisionError(message)

    seen = [one.index for one in decisions]
    if len(seen) != len(set(seen)):
        message = f"决策的 index 有重复：{sorted(seen)}"
        raise DecisionError(message)
    if set(seen) != set(range(expected)):
        message = f"决策要覆盖全部 {expected} 个待确认调用，收到的 index 是 {sorted(seen)}"
        raise DecisionError(message)

    for one in decisions:
        if one.type is DecisionType.EDIT and one.edited_action is None:
            message = f"index={one.index} 是 edit，但没给 edited_action"
            raise DecisionError(message)
        if one.type is DecisionType.RESPOND and not (one.message or "").strip():
            message = f"index={one.index} 是 respond，但没给要回给 agent 的话"
            raise DecisionError(message)


def to_resume(decisions: list[Decision]) -> list[dict[str, object]]:
    """按 `index` 重排，转成 DeepAgents 认的形状。

    **重排在这里做，不让前端保证顺序** —— 那个约束透出去迟早会出错，
    而它出错的方式是把 A 的决策套到 B 的调用上。

    Args:
        decisions: 已经校验过的决策。

    Returns:
        与 `action_requests` 同序的决策列表。
    """
    return [_one(decision) for decision in sorted(decisions, key=lambda one: one.index)]


def _one(decision: Decision) -> dict[str, object]:
    payload: dict[str, object] = {"type": decision.type.value}
    if decision.type is DecisionType.EDIT and decision.edited_action is not None:
        payload["edited_action"] = {
            "name": decision.edited_action.name,
            "args": decision.edited_action.args,
        }
    elif decision.message is not None:
        payload["message"] = decision.message
    return payload
