"""结果聚合的测试。

跑法（不进两端门禁，评估工具不属于平台运行时）：
    PYTHONPATH=script/eval src/.venv/bin/python -m pytest script/eval
"""

import pytest

from run_eval import _cost_spread


def row(item_id: str, cost: float) -> dict[str, object]:
    return {"item_id": item_id, "cost_yuan": cost}


def test_the_spread_is_relative_not_absolute() -> None:
    """必须取相对值，否则最贵那道题一个人就把噪声带定死了。

    首轮实测各题绝对成本差二十倍（0.06 元到 1.30 元）：便宜那题翻一倍才 0.06 元的极差，
    而贵那题波动百分之几就有 0.05 元 —— 按绝对值排，便宜题的剧烈波动永远排不上号。
    """
    rows = [
        row("cheap", 0.01),
        row("cheap", 0.02),
        row("pricey", 1.00),
        row("pricey", 1.05),
    ]

    # cheap 翻了一倍（1.0），pricey 只动了百分之五
    assert _cost_spread(rows) == 1.0


def test_a_single_replicate_yields_no_spread() -> None:
    """一个点算不出极差 —— 报 0 等于宣称这批毫无波动，那是假红的来源。"""
    assert _cost_spread([row("only", 0.5)]) is None


def test_a_zero_cost_row_is_skipped_instead_of_dividing_by_zero() -> None:
    """成本为零的那组不参与，而不是让整批算崩。

    零成本意味着这次 run 根本没跑起来（token 全零），它的「相对波动」没有意义。
    """
    rows = [row("dead", 0.0), row("dead", 0.0), row("live", 0.10), row("live", 0.12)]

    assert _cost_spread(rows) == pytest.approx(0.2)
