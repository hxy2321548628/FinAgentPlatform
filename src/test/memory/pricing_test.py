"""记忆辅助调用的人民币成本换算。"""

import pytest

from app.event.model import TokenUsage
from app.memory.pricing import ModelTokenPrice, TokenPrice


def test_each_token_class_uses_its_own_per_million_price() -> None:
    price = TokenPrice(cached=0.1, uncached=3, output=9)

    cost = price.cost(
        TokenUsage(
            input_cache_read=1_000_000,
            input_uncached=2_000_000,
            output=3_000_000,
        )
    )

    assert cost == pytest.approx(0.1 + 6 + 27)


def test_an_explicitly_skipped_stage_costs_zero() -> None:
    assert TokenPrice(cached=0.1, uncached=3, output=9).cost(TokenUsage()) == 0


def test_a_price_cannot_be_silently_reused_after_the_model_changes() -> None:
    cost = ModelTokenPrice(model="aux-v1", price=TokenPrice(cached=0.1, uncached=3, output=9))

    with pytest.raises(ValueError, match="没有配置"):
        cost.yuan("aux-v2", TokenUsage(input_uncached=1))
