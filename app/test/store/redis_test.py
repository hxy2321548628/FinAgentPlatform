"""Redis 接入的测试。"""

import asyncio

import pytest
from redis.asyncio import Redis
from redis.exceptions import TimeoutError as RedisTimeoutError

from config import StoreSettings
from run.log import DEFAULT_BLOCK_MILLISECOND as EVENT_BLOCK
from store.redis import DEFAULT_SOCKET_TIMEOUT, RedisUnavailableError, check, create_client
from task.queue import DEFAULT_BLOCK_MILLISECOND as TASK_BLOCK
from test.conftest import TEST_DATABASE

# 一个不会有人监听的端口
DEAD_URL = "redis://127.0.0.1:1/0"

# 业务用的那个 URL 的形状：**末尾带库号**，而那正是覆盖出问题的地方
BUSINESS_URL = "redis://127.0.0.1:6379/0"
BUSINESS_DATABASE = 0

# 演示故障模式用：故意把 socket 超时压到比 BLOCK 还短
IMPATIENT_SECOND = 0.2
PATIENT_BLOCK_MILLISECOND = 1_000


async def test_check_raises_when_redis_is_unreachable() -> None:
    dead = create_client(DEAD_URL)
    try:
        with pytest.raises(RedisUnavailableError):
            await check(dead)
    finally:
        await dead.aclose()


async def test_check_passes_against_a_live_redis(live_cache: Redis) -> None:
    await check(live_cache)


def test_the_database_argument_beats_the_database_in_the_url() -> None:
    """`Redis.from_url(url, db=15)` 会被 URL 里的 `/0` **静默**盖掉。

    而业务的 URL 正是以 `/0` 结尾。后果有两层，都不报错：每条用例开头的 `flushdb`
    冲的是业务库，正在跑的 run 的事件与排队中的任务一起没；投出去的测试任务被真的
    worker 领走，那是要花钱的模型调用，而事件流里会冒出没人写过的真实回答。
    """
    client = create_client(BUSINESS_URL, database=TEST_DATABASE)

    assert client.connection_pool.connection_kwargs["db"] == TEST_DATABASE


def test_no_database_argument_keeps_the_one_in_the_url() -> None:
    """业务进程不传这个参数，库号就该由 URL 说了算。"""
    client = create_client(BUSINESS_URL)

    assert client.connection_pool.connection_kwargs["db"] == BUSINESS_DATABASE


def test_the_socket_timeout_outlives_every_blocking_command() -> None:
    """Socket 超时短于 BLOCK 时长的话，空闲的 worker 会一直刷 TimeoutError。

    redis-py 8 的默认 socket 超时正好是 5 秒，与两处 `BLOCK 5000` 撞在一起 ——
    这个坑是部署之后才冒出来的，单测里的阻塞从没真的等满过一轮。
    """
    assert max(EVENT_BLOCK, TASK_BLOCK) / 1000 < DEFAULT_SOCKET_TIMEOUT


async def test_a_blocking_read_dies_when_the_socket_gives_up_first(live_cache: Redis) -> None:
    """上一条守的是什么，这一条演示给你看：超时压到 BLOCK 之下，阻塞读就炸。"""
    impatient = Redis.from_url(
        StoreSettings().redis_url, db=TEST_DATABASE, decode_responses=True, socket_timeout=IMPATIENT_SECOND
    )
    try:
        with pytest.raises(RedisTimeoutError):
            await impatient.xread({"zuel:test:never": "0-0"}, block=PATIENT_BLOCK_MILLISECOND)
    finally:
        await impatient.aclose()


async def test_a_blocking_read_survives_a_full_block_window(live_cache: Redis) -> None:
    """默认客户端要能等满一整轮 —— worker 空闲时每 5 秒就是这么等一次。"""
    async with asyncio.timeout(PATIENT_BLOCK_MILLISECOND / 1000 + 5):
        assert await live_cache.xread({"zuel:test:never": "0-0"}, block=PATIENT_BLOCK_MILLISECOND) in (None, [], {})


async def test_the_client_decodes_replies_to_text(live_cache: Redis) -> None:
    """事件信封是 JSON 文本。客户端不解码的话，每个调用方都得自己 decode 一遍。"""
    key = "zuel:test:decode"
    await live_cache.set(key, "行业分布")
    try:
        assert await live_cache.get(key) == "行业分布"
    finally:
        await live_cache.delete(key)
