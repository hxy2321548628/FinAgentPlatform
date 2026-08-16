"""向 Langfuse 要用量：全平台总量、某个人的用量、按人排行。

**用量的账本在 Langfuse 那边，不在这里。** 平台自己的 `runs.tokens_*` 仍然逐条落库，
但它只服务配额闸门那一个用途 —— 两份账本各自回答一个问题，谁都不去回答对方那个，
这样它们分叉时也不会有人被误导（`quota/usage.py` 开头拒绝 Redis 计数器时是同一个理由）。

**这一层最容易写成「看着对但答案是 0」。** Langfuse 会为一个构造错的查询返回 200 与
一个形状正确的空结果。P11 开工时量到的正是这个：接口全部 200、有数据，而按用户
切出来每人都是 0（真因是身份没落到 GENERATION span 上，已在 `agent/trace.py` 修掉）。
因此这里**不吞任何非 2xx** —— 「用量是 0」与「查询写错了」必须长得不一样。
"""

import json
from dataclasses import dataclass
from datetime import datetime

import httpx

# Langfuse v2 metrics 的路径。**v1 那个在 v4 的 events_only 模式下整个 404**，
# 且它的文档还活着 —— 照文档写会得到一个查不通的实现
METRICS_PATH = "/api/public/v2/metrics"

# 按什么口径取数。`observations` 是唯一带 token 的视图
VIEW = "observations"

# 排行默认取前多少名
DEFAULT_LIMIT = 20


@dataclass(frozen=True)
class Usage:
    """一段窗口里的用量。"""

    tokens: int
    cost: float
    observations: int


@dataclass(frozen=True)
class UserUsage(Usage):
    """一个人在一段窗口里的用量。"""

    user_id: str


class LangfuseUsage:
    """按窗口向 Langfuse 取用量。

    Args:
        client: 到 Langfuse 的异步客户端，`base_url` 要已经指向它。
        public_key: Langfuse 项目的 public key。
        secret_key: 对应的 secret key。
    """

    def __init__(self, *, client: httpx.AsyncClient, public_key: str, secret_key: str) -> None:
        self._client = client
        self._auth = (public_key, secret_key)

    async def total(self, *, since: datetime, until: datetime) -> Usage:
        """全平台在这段窗口里的用量。

        Args:
            since: 窗口起点。
            until: 窗口终点。

        Returns:
            token、费用与 observation 条数。

        Raises:
            httpx.HTTPStatusError: Langfuse 拒绝了这次查询。
        """
        rows = await self._query(self._window(since, until))
        return _to_usage(rows[0] if rows else {})

    async def of_user(self, user_id: str, *, since: datetime, until: datetime) -> Usage:
        """某一个人在这段窗口里的用量。

        **用 filter 而不是分组** —— 分组是给排行用的，查一个人时它既更贵也更绕。

        Args:
            user_id: 平台的用户标识，与 trace 上带的那个是同一个。
            since: 窗口起点。
            until: 窗口终点。

        Returns:
            这个人的 token、费用与 observation 条数。

        Raises:
            httpx.HTTPStatusError: Langfuse 拒绝了这次查询。
        """
        query = self._window(since, until)
        query["filters"] = [{"column": "userId", "operator": "=", "value": user_id, "type": "string"}]
        rows = await self._query(query)
        return _to_usage(rows[0] if rows else {})

    async def by_user(self, *, since: datetime, until: datetime, limit: int = DEFAULT_LIMIT) -> list[UserUsage]:
        """按人排行，用得最多的在前面。

        **`config.row_limit` 与降序的 `orderBy` 两样都不能少。** `userId` 是高基数
        维度，缺任一样 Langfuse 直接 400（实测：「High cardinality dimension(s)
        'userId' require both 'config.row_limit' and 'orderBy' ...」）。它的文档写的是
        「不能用它分组」，而实际是「要多带两个参数」—— 照文档写会白白砍掉一个
        做得到的功能。

        Args:
            since: 窗口起点。
            until: 窗口终点。
            limit: 最多取几个人。

        Returns:
            按 token 降序的用量，**不含没有主人的那一行**。

        Raises:
            httpx.HTTPStatusError: Langfuse 拒绝了这次查询。
        """
        query = self._window(since, until)
        query["dimensions"] = [{"field": "userId"}]
        query["orderBy"] = [{"field": "sum_totalTokens", "direction": "desc"}]
        query["config"] = {"row_limit": limit}
        rows = await self._query(query)
        found: list[UserUsage] = []
        for row in rows:
            # **没有主人的那一行要扔掉。** 把它显示出来，排行第一名就永远是
            # 「未知用户」——那一行说明不了任何人的用量
            owner = row.get("userId")
            if not isinstance(owner, str) or not owner:
                continue
            base = _to_usage(row)
            found.append(UserUsage(user_id=owner, tokens=base.tokens, cost=base.cost, observations=base.observations))
        return found

    def _window(self, since: datetime, until: datetime) -> dict[str, object]:
        return {
            "view": VIEW,
            "metrics": [
                {"measure": "totalTokens", "aggregation": "sum"},
                {"measure": "totalCost", "aggregation": "sum"},
                {"measure": "count", "aggregation": "count"},
            ],
            "fromTimestamp": since.isoformat(),
            "toTimestamp": until.isoformat(),
        }

    async def _query(self, query: dict[str, object]) -> list[dict[str, object]]:
        response = await self._client.get(METRICS_PATH, params={"query": json.dumps(query)}, auth=self._auth)
        response.raise_for_status()
        body = response.json()
        rows = body.get("data", []) if isinstance(body, dict) else []
        return [one for one in rows if isinstance(one, dict)]


def _to_usage(row: dict[str, object]) -> Usage:
    """把一行读成用量。

    **缺的 measure 按 0 算** —— Langfuse 会省掉没有数据的那些，
    那表示「这段时间没人用」，不是故障。
    """
    return Usage(
        tokens=_int(row.get("sum_totalTokens")),
        cost=_float(row.get("sum_totalCost")),
        observations=_int(row.get("count_count")),
    )


def _int(value: object) -> int:
    return int(value) if isinstance(value, int | float) else 0


def _float(value: object) -> float:
    return float(value) if isinstance(value, int | float) else 0.0
