"""三道闸的档位：每个角色能用多少。

**这里的每一个初值都是从同一个样本外推出来的**，不是精算结果。平台还没有真实用户
（没有前端，所有样本都是验收脚本跑的同一个 case），而「阈值为空的闸不是闸」——
上线时若没有任何成本闸门，LLM 调用是真金白银。因此这是**明知证据不足仍先定一版**，
靠可配置与写清外推方式留出校准的余地。

**每个常量旁边都写了它是怎么来的。** 一个来路不明的常数比没有常数更难改 ——
后来的人不知道它是精心算的还是随手写的，只好不敢动。

校准的入口：每跑一次验收就记一次真实的未命中 token 数，攒成分布再回来改这几个数。
"""

from dataclasses import dataclass
from types import MappingProxyType

from user.model import UserRole

# 一次完整分析的实测当量（架构 §6.4，2026-08-02 P0 探针）：
# 未命中 input 115,328 + output 8,701 ≈ 12.4 万。下面两组初值都从这一个数外推
ANALYSIS_TOKEN = 124_000

# output 与未命中 input 的当量权重。**目前 1:1** —— 手里没有可核对的价目表，
# 而拍一个比 1 更「精确」的数字，只会让后来的人以为它是算出来的。
# 架构 §6.4 真正要求的是「cache_read 不计入」，那一条由计量口径本身保证，不靠这个权重
DEFAULT_OUTPUT_WEIGHT = 1

# 日配额 = 单次当量 × 保守的日均次数：teacher 按每天 8 次深度分析（12.4 万 × 8 ≈ 99 万，
# 取整 100 万），student 按 3 次（≈ 37 万，取整 40 万）。
#
# **教师与学生的权限完全相同，配额是二者唯一的实质差别**，也是控制成本的唯一手段 ——
# 学生人数通常远多于教师，配额若相同，成本结构会由学生侧主导。
# admin 与 teacher 同档：管理员的会话与教师同权，它多的只是管账号的能力
DEFAULT_TOKEN_DAILY = MappingProxyType(
    {
        UserRole.ADMIN: 1_000_000,
        UserRole.TEACHER: 1_000_000,
        UserRole.STUDENT: 400_000,
    }
)

# 并发 run 上限 = 沙箱池容量 / 预期同时在线人数：架构 §8.1 建议配 20 个沙箱，
# §2.2 的量级是「同时在跑个位数到几十」，按 10 人算得 2。教师人数少，多给一个。
#
# 这道闸拦的是「单个用户占满整个沙箱池」，因此它必须明显小于池容量本身
DEFAULT_CONCURRENT_RUN = MappingProxyType(
    {
        UserRole.ADMIN: 3,
        UserRole.TEACHER: 3,
        UserRole.STUDENT: 2,
    }
)

# 接口频率：按「一个人正常操作的手速」定，**宁松勿紧** —— 另外两道闸至少还对应着
# 真实的资源占用，这一道拦的往往只是手快，误伤的是正常用户。
# 每分钟 120 次即每秒 2 次，人手点不出来；而 SSE 是长连接，整条流只算一次
DEFAULT_RATE_LIMIT = 120
DEFAULT_RATE_WINDOW_SECOND = 60


@dataclass(frozen=True)
class Allowance:
    """一个用户此刻的三个上限。"""

    token_daily: int
    concurrent_run: int


class QuotaPolicy:
    """按角色定档，允许逐个用户覆盖。

    **用户那两列留空表示「跟着角色的档走」**，不是「没有配额」：默认档在配置里，
    调一次就对所有没被单独调整过的人生效。建号时把默认值抄进行里的话，
    改配置只影响之后新建的账号。

    Args:
        token_daily: 各角色的 token 日配额。
        concurrent_run: 各角色的并发 run 上限。
        output_weight: output token 折算成当量时的权重。
    """

    def __init__(
        self,
        *,
        token_daily: dict[UserRole, int] | None = None,
        concurrent_run: dict[UserRole, int] | None = None,
        output_weight: int = DEFAULT_OUTPUT_WEIGHT,
    ) -> None:
        self._token_daily = dict(token_daily or DEFAULT_TOKEN_DAILY)
        self._concurrent_run = dict(concurrent_run or DEFAULT_CONCURRENT_RUN)
        self._output_weight = output_weight

    @property
    def output_weight(self) -> int:
        """折算 output token 时用的权重。"""
        return self._output_weight

    def allow(self, *, role: UserRole, token_daily: int | None, concurrent_run: int | None) -> Allowance:
        """算出某个用户此刻的上限。

        Args:
            role: 角色。
            token_daily: 该用户的 token 配额覆盖，留空则跟角色的档。
            concurrent_run: 该用户的并发覆盖，留空则跟角色的档。

        Returns:
            这个用户的三个上限。
        """
        return Allowance(
            token_daily=token_daily if token_daily is not None else self._token_daily[role],
            concurrent_run=concurrent_run if concurrent_run is not None else self._concurrent_run[role],
        )
