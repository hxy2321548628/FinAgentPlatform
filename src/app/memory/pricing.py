"""记忆辅助模型 token 到人民币成本的显式换算。"""

from dataclasses import dataclass

from app.event.model import TokenUsage

PRICE_UNIT = 1_000_000


@dataclass(frozen=True)
class TokenPrice:
    """三类 token 的每百万个人民币单价。"""

    cached: float
    uncached: float
    output: float

    def cost(self, usage: TokenUsage) -> float:
        """按实际三段用量换算成本。"""
        return (
            usage.input_cache_read * self.cached + usage.input_uncached * self.uncached + usage.output * self.output
        ) / PRICE_UNIT


@dataclass(frozen=True)
class ModelTokenPrice:
    """把一组单价绑定到明确模型名，防止模型切换后沿用旧价。"""

    model: str
    price: TokenPrice

    def yuan(self, model: str, tokens: TokenUsage) -> float:
        """按模型名校验后换算人民币成本。"""
        if model != self.model:
            raise ValueError(f"模型 {model!r} 没有配置记忆辅助调用单价")
        return self.price.cost(tokens)
