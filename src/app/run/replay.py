"""事件回放：把实时流压成一次性取回的形状。

`token` 与 `reasoning` 在实时流里是逐个增量推的 —— 那是打字机效果的前提。
**翻旧账没有这个前提**：一轮实测 10873 条、2.4 MB，全下一遍既慢又要让前端
把同一段文本追加上万次。相邻的同类增量在这里合成一条，条数与体积都降两个
数量级，而前端把增量拼进同一段的结果与合并前完全一样。

**只合并相邻的、同类且同 path 的那些。** 跨过工具调用去合并会让文本前后颠倒；
跨 path 合并会把两个子 agent 的话混成一句；把 token 与 reasoning 合到一起
会让思考和结论渲染成一段。
"""

from collections.abc import Sequence

from app.event.model import EventType, ReasoningData, TokenData
from app.run.log import LoggedEvent

# 只有这两类是「同一段文本的增量」，其余事件各自独立，合并没有意义
MERGEABLE_TYPE = frozenset({EventType.TOKEN, EventType.REASONING})


def collapse(events: Sequence[LoggedEvent]) -> list[LoggedEvent]:
    """把相邻的同类增量合并成一条。

    Args:
        events: 按发生顺序排列的事件。

    Returns:
        同样按发生顺序排列，相邻同类增量已合并。合并后的那条带着这一段里
        **最后**一条的 id 与时间戳 —— id 是「读到这里为止」的游标。
    """
    collapsed: list[LoggedEvent] = []
    for logged in events:
        previous = collapsed[-1] if collapsed else None
        if previous is not None and _mergeable(previous, logged):
            collapsed[-1] = _merge(previous, logged)
            continue
        collapsed.append(logged)
    return collapsed


def _mergeable(previous: LoggedEvent, current: LoggedEvent) -> bool:
    """这两条是不是同一段文本的相邻增量。"""
    return (
        current.event.type in MERGEABLE_TYPE
        and previous.event.type == current.event.type
        and previous.event.path == current.event.path
    )


def _merge(previous: LoggedEvent, current: LoggedEvent) -> LoggedEvent:
    """把后一条的文本接到前一条上，位置与时间戳取后一条的。"""
    head, tail = previous.event.data, current.event.data
    if not isinstance(head, TokenData | ReasoningData) or not isinstance(tail, TokenData | ReasoningData):
        raise TypeError(f"这两类事件的载荷必须带 text：{previous.event.type}")
    joined = head.model_copy(update={"text": head.text + tail.text})
    return LoggedEvent(id=current.id, event=current.event.model_copy(update={"data": joined}))
