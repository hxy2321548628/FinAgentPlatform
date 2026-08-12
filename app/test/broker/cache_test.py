"""写操作去重表的测试，连真 Redis。

**要防的是崩溃路径的重复执行**：崩溃在工具执行途中时那个图节点会整个重跑，
于是 `edit_file` 的 `old_string` 已经不在了、`delete` 的文件已经没了 ——
两者都会返回一个**首次执行时没有的错误**，使 LLM 的后续行为偏离。
"""

from uuid import uuid4

import pytest
from redis.asyncio import Redis

from broker.cache import KEY_PREFIX, ToolCache
from test.conftest import json_log

SHORT_TTL_SECOND = 60

NS = "tools:fd422cb9-d8b8-c0ae-510d-64ed2e099a1c"

# 不会有人监听的端口，连不上是立刻的 ECONNREFUSED
DEAD_PORT = 1


@pytest.fixture
def cache(live_cache: Redis) -> ToolCache:
    return ToolCache(live_cache, ttl_second=SHORT_TTL_SECOND)


async def test_a_call_that_never_ran_has_nothing_cached(cache: ToolCache) -> None:
    assert await cache.get(uuid4().hex, NS) is None


async def test_a_recorded_result_comes_back_unchanged(cache: ToolCache) -> None:
    thread_id = uuid4().hex

    await cache.put(thread_id, NS, {"error": None, "path": "/workspace/a.csv"})

    assert await cache.get(thread_id, NS) == {"error": None, "path": "/workspace/a.csv"}


async def test_an_error_result_is_cached_too(cache: ToolCache) -> None:
    """出错的结果也要记。

    **只缓存成功等于没解决问题**：重放时 `old_string` 已经不在，那个错误正是首次执行
    没有的，不缓存的话 LLM 就会看到它，后续行为随之偏离。
    """
    thread_id = uuid4().hex

    await cache.put(thread_id, NS, {"error": "找不到要替换的串", "path": None})

    assert await cache.get(thread_id, NS) == {"error": "找不到要替换的串", "path": None}


async def test_two_calls_in_the_same_round_do_not_collide(cache: ToolCache) -> None:
    """LangGraph 把同一轮的每个工具调用扇出成独立 task，因此 ns 按**调用**唯一。

    **这条用例是那个假设的守卫**：若框架改变扇出粒度（把同一轮的多个调用合成一个
    task），第二次调用就会直接拿到第一次的结果 —— 而它坏掉的方式是静默的。
    升级 langgraph 之后必须重跑它。
    """
    thread_id = uuid4().hex
    first, second = "tools:fd422cb9", "tools:3ad455cb"

    await cache.put(thread_id, first, {"path": "/workspace/a.txt"})
    await cache.put(thread_id, second, {"path": "/workspace/b.txt"})

    assert await cache.get(thread_id, first) == {"path": "/workspace/a.txt"}
    assert await cache.get(thread_id, second) == {"path": "/workspace/b.txt"}


async def test_two_threads_do_not_collide(cache: ToolCache) -> None:
    """键里带 thread_id：不同会话的 ns 撞上了也不能互相看见对方的结果。"""
    await cache.put("甲", NS, {"path": "甲的"})
    await cache.put("乙", NS, {"path": "乙的"})

    assert await cache.get("甲", NS) == {"path": "甲的"}


async def test_the_record_expires_by_itself(live_cache: Redis, cache: ToolCache) -> None:
    thread_id = uuid4().hex

    await cache.put(thread_id, NS, {"path": "/workspace/a.csv"})

    assert 0 < await live_cache.ttl(f"{KEY_PREFIX}{thread_id}:{NS}") <= SHORT_TTL_SECOND


async def test_an_oversized_result_is_not_cached(live_cache: Redis) -> None:
    """截断后缓存比不去重更糟 —— 那份结果与首次执行的不一致。"""
    cache = ToolCache(live_cache, ttl_second=SHORT_TTL_SECOND, max_byte=64)
    thread_id = uuid4().hex

    await cache.put(thread_id, NS, {"output": "长" * 1000})

    assert await cache.get(thread_id, NS) is None


async def test_an_unreachable_cache_degrades_instead_of_breaking_the_tool() -> None:
    """**去重表是崩溃路径上的一道保险，不是执行的前提。**

    Redis 连不上时让每一次写操作都 500，代价比「这段时间没有去重」大得多。
    但它必须吼出来 —— 那期间重放是会真的重跑的。
    """
    unreachable = ToolCache(Redis(host="127.0.0.1", port=DEAD_PORT, socket_connect_timeout=1))

    with json_log("broker.cache") as recorded:
        assert await unreachable.get("甲", NS) is None
        await unreachable.put("甲", NS, {"path": "/workspace/a.csv"})

    assert [one["level"] for one in recorded] == ["WARNING", "WARNING"]
