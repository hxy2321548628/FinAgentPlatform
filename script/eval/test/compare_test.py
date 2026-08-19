"""跨轮对比的测试。

**只验两件事**：老记录的成本能不能复算对、极差算不出来时会不会假装有数。
两件都是「错了不会报错，只会给出一个看着很正常的数」。

跑法：
    PYTHONPATH=script/eval src/.venv/bin/python -m pytest script/eval
"""

from compare import cost_of_record, spread
from metric import cost_of


def test_a_new_record_uses_its_own_cost_field() -> None:
    """记录里带了 `cost_yuan` 就用它，不要拿 token 再算一遍。"""
    assert cost_of_record({"cost_yuan": 0.5, "tokens_uncached": 999_999}) == 0.5


def test_an_old_record_is_recomputed_from_its_token_counts() -> None:
    """**早期几轮没有 `cost_yuan`**（主判据改口之后才加的字段）。

    不复算就只能拿命中率去比 —— 那正是首轮判错方向的原因。
    """
    old = {"tokens_cache_read": 1_000_000, "tokens_uncached": 0, "tokens_output": 0}

    assert cost_of_record(old) == cost_of(cached=1_000_000, uncached=0, output=0)


def test_a_record_missing_every_token_field_costs_zero_not_crash() -> None:
    """失败的 run 可能一个 token 字段都没有，这时该是 0 而不是抛异常中断整张表。"""
    assert cost_of_record({"item_id": "E01", "status": "failed"}) == 0.0


def test_spread_needs_at_least_two_copies() -> None:
    """一个副本算不出极差。**报 0 会被读成「这题一点波动都没有」** —— 那是假数。"""
    assert spread([0.1]) is None
    assert spread([]) is None


def test_spread_is_relative_not_absolute() -> None:
    """各题绝对成本差二十倍，按绝对值排的话便宜题翻一倍永远排不上号。"""
    assert spread([0.1, 0.2]) == 1.0
    assert spread([1.0, 2.0]) == 1.0
