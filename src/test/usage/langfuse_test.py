"""向 Langfuse 要用量：查询怎么构造、返回怎么解析。

**这一层最容易写成「看着对但答案是 0」。** Langfuse 会为一个构造错的查询返回 200
与一个形状正确的空结果 —— 按用户切出来每人都是 0，而没有任何一处报错。
因此这里的用例盯的是查询本身长什么样，不只是解析。
"""

import json
from datetime import UTC, datetime

import httpx
import pytest

from app.usage.langfuse import LangfuseUsage

BASE_URL = "http://langfuse.test"

PUBLIC_KEY = "pk-lf-test"

SECRET_KEY = "sk-lf-test"

SINCE = datetime(2026, 8, 1, tzinfo=UTC)

UNTIL = datetime(2026, 8, 31, tzinfo=UTC)


def a_usage(handler: object) -> LangfuseUsage:
    """一个连着假传输层的用量客户端。"""
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=BASE_URL)  # type: ignore[arg-type]
    return LangfuseUsage(client=client, public_key=PUBLIC_KEY, secret_key=SECRET_KEY)


def captured(rows: list[dict[str, object]]) -> tuple[list[dict[str, object]], object]:
    """记下每次查询，并按给定的行作答。"""
    seen: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.url.params["query"]))
        return httpx.Response(200, json={"data": rows})

    return seen, handler


async def test_a_per_user_query_carries_the_two_things_langfuse_demands() -> None:
    """**没有这两项，Langfuse 直接 400。**

    `userId` 是高基数维度，用它分组必须同时给 `config.row_limit` 与一个
    降序的 `orderBy`。实测过：少了它们返回的是
    「High cardinality dimension(s) 'userId' require both ...」。

    文档里写的是「不能用它分组」，实际是「要多带两个参数」—— 照文档写会白白
    砍掉一个做得到的功能，照错误信息写才对。
    """
    seen, handler = captured([])

    await a_usage(handler).by_user(since=SINCE, until=UNTIL, limit=10)

    assert seen[0]["dimensions"] == [{"field": "userId"}]
    assert seen[0]["config"] == {"row_limit": 10}
    order = seen[0]["orderBy"]
    assert isinstance(order, list)
    assert order[0]["direction"] == "desc"


async def test_a_single_user_query_filters_instead_of_grouping() -> None:
    """查一个人不必分组 —— 分组是给排行用的，这里用 filter 更省也更准。"""
    seen, handler = captured([])

    await a_usage(handler).of_user("teacher-1", since=SINCE, until=UNTIL)

    assert seen[0].get("dimensions", []) == []
    assert seen[0]["filters"] == [{"column": "userId", "operator": "=", "value": "teacher-1", "type": "string"}]


async def test_the_window_is_sent_as_the_two_timestamps() -> None:
    """窗口错了的话数字仍然「对」，只是对的是另一个月。"""
    seen, handler = captured([])

    await a_usage(handler).total(since=SINCE, until=UNTIL)

    assert seen[0]["fromTimestamp"] == SINCE.isoformat()
    assert seen[0]["toTimestamp"] == UNTIL.isoformat()


async def test_a_ranking_is_read_back_row_by_row() -> None:
    _, handler = captured(
        [
            {"userId": "teacher-1", "sum_totalTokens": 5000, "sum_totalCost": 0.5, "count_count": 3},
            {"userId": "teacher-2", "sum_totalTokens": 1000, "sum_totalCost": 0.1, "count_count": 1},
        ]
    )

    ranking = await a_usage(handler).by_user(since=SINCE, until=UNTIL, limit=10)

    assert [one.user_id for one in ranking] == ["teacher-1", "teacher-2"]
    assert ranking[0].tokens == 5000
    assert ranking[0].cost == pytest.approx(0.5)
    assert ranking[0].observations == 3


async def test_rows_without_a_user_are_dropped() -> None:
    """**没有主人的那一行要扔掉，不能当成一个叫 null 的用户。**

    P11 开工时库里正是这个形状：7,118,137 个 token 全记在 userId=null 上。
    把它显示出来，排行第一名就永远是「未知用户」，而那一行说明不了任何人的用量。
    """
    _, handler = captured(
        [
            {"userId": None, "sum_totalTokens": 7118137, "sum_totalCost": 0, "count_count": 4253},
            {"userId": "teacher-1", "sum_totalTokens": 5000, "sum_totalCost": 0.5, "count_count": 3},
        ]
    )

    ranking = await a_usage(handler).by_user(since=SINCE, until=UNTIL, limit=10)

    assert [one.user_id for one in ranking] == ["teacher-1"]


async def test_a_missing_measure_reads_as_zero_not_as_a_crash() -> None:
    """Langfuse 会省掉没有数据的 measure —— 那是「这段时间没人用」，不是故障。"""
    _, handler = captured([{}])

    found = await a_usage(handler).total(since=SINCE, until=UNTIL)

    assert found.tokens == 0
    assert found.cost == 0


async def test_an_empty_result_is_zero_usage() -> None:
    _, handler = captured([])

    found = await a_usage(handler).total(since=SINCE, until=UNTIL)

    assert found.tokens == 0
    assert found.observations == 0


async def test_langfuse_refusing_the_query_is_not_swallowed() -> None:
    """**查询构造错了必须炸出来。**

    吞掉 400 返回 0 的话，「用量是 0」与「查询写错了」就长得一模一样 ——
    而这两件事一个该去问教师，一个该去改代码。
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"message": "High cardinality dimension(s) 'userId' ..."})

    with pytest.raises(httpx.HTTPStatusError):
        await a_usage(handler).by_user(since=SINCE, until=UNTIL, limit=10)
