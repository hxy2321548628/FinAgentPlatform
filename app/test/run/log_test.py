"""事件日志的测试，连真 Redis。

**断言与内存版那一版是同一套**：id 的形状、游标语义、`follow` 的收尾条件都没变，
换掉的只是实现。这正是 `EventLog` 这层抽象存在的意义 ——
测试不该因为换了实现而重写。

只有两处跟着实现变了，且都是因为约束本身消失了：
`append` 成了 IO，所以要 `await`；`max_run` 那条上限没了 —— 一个 run 一条 Stream，
是各自独立的键，不再有「同时保留几个 run」这回事，按时间的保留策略在步骤五。
"""

import asyncio

import pytest
from redis.asyncio import Redis

from event.model import (
    Event,
    EventType,
    RunErrorCode,
    RunFailedData,
    RunFailedEvent,
    RunFinishedData,
    RunFinishedEvent,
    TokenData,
    TokenEvent,
)
from run.log import EventLog, InvalidEventIdError


def token(text: str, run_id: str = "run-1") -> Event:
    return TokenEvent(ts=1, run_id=run_id, path=(), data=TokenData(text=text))


def finished(run_id: str = "run-1") -> Event:
    return RunFinishedEvent(ts=1, run_id=run_id, path=(), data=RunFinishedData(tokens_used=0))


def failed(run_id: str = "run-1") -> Event:
    return RunFailedEvent(
        ts=1,
        run_id=run_id,
        path=(),
        data=RunFailedData(code=RunErrorCode.INTERNAL, message="炸了", retryable=False),
    )


@pytest.fixture
def log(live_cache: Redis) -> EventLog:
    return EventLog(live_cache)


# ------------------------------------------------------------------ 追加与 id
async def test_append_returns_a_redis_stream_shaped_id(log: EventLog) -> None:
    logged = await log.append(token("你"))

    millisecond, _, sequence = logged.id.partition("-")
    assert millisecond.isdigit()
    assert sequence.isdigit()


async def test_ids_increase_monotonically_within_one_run(log: EventLog) -> None:
    ids = [(await log.append(token(str(index)))).id for index in range(50)]

    assert ids == sorted(ids, key=lambda one: tuple(int(part) for part in one.split("-")))
    assert len(set(ids)) == len(ids)


async def test_ids_stay_unique_when_events_land_in_the_same_millisecond(log: EventLog) -> None:
    """毫秒精度不够分辨相邻事件，序号那一段就是为此存在的。"""
    ids = [(await log.append(token(str(index)))).id for index in range(200)]
    milliseconds = {one.split("-")[0] for one in ids}

    assert len(milliseconds) < len(ids)
    assert len(set(ids)) == len(ids)


async def test_ids_are_allocated_per_run_not_globally(log: EventLog) -> None:
    """两个 run 的事件流互不相干，各自从头编号。"""
    await log.append(token("a", run_id="run-1"))
    await log.append(token("b", run_id="run-2"))

    assert [one.event.data.text for one in await log.read("run-1")] == ["a"]  # type: ignore[union-attr]
    assert [one.event.data.text for one in await log.read("run-2")] == ["b"]  # type: ignore[union-attr]


# ------------------------------------------------------------------ 读取与重放
async def test_read_without_cursor_returns_the_whole_run(log: EventLog) -> None:
    await log.append(token("一"))
    await log.append(token("二"))

    assert len(await log.read("run-1")) == 2


async def test_read_after_a_cursor_skips_what_the_client_already_has(log: EventLog) -> None:
    first = await log.append(token("一"))
    await log.append(token("二"))
    await log.append(token("三"))

    replayed = await log.read("run-1", after=first.id)

    assert [one.event.data.text for one in replayed] == ["二", "三"]  # type: ignore[union-attr]


async def test_replay_from_any_id_loses_nothing_and_repeats_nothing(log: EventLog) -> None:
    """断线重连的核心保证：每个位置断开，补齐的部分与已收到的部分严丝合缝。"""
    logged = [await log.append(token(str(index))) for index in range(20)]

    for cut in range(len(logged)):
        received = logged[: cut + 1]
        replayed = await log.read("run-1", after=received[-1].id)

        assert [one.id for one in received] + [one.id for one in replayed] == [one.id for one in logged]


async def test_read_after_the_last_id_returns_nothing(log: EventLog) -> None:
    last = await log.append(token("一"))

    assert await log.read("run-1", after=last.id) == []


async def test_read_of_an_unknown_run_returns_nothing(log: EventLog) -> None:
    assert await log.read("never-existed") == []


async def test_cursor_ordering_is_numeric_not_lexicographic(log: EventLog) -> None:
    """`10-0` 字符串比较小于 `9-0`，直接比字符串会把整段历史当成未读重发。"""
    assert await log.read("run-1", after="9-0") == []
    await log.append(token("一"))
    assert await log.read("run-1", after="99999999999999-0") == []


@pytest.mark.parametrize("cursor", ["", "abc", "1-", "-0", "1-2-3", "x-y", "1.5-0"])
async def test_a_malformed_cursor_is_rejected(log: EventLog, cursor: str) -> None:
    """游标来自客户端的 Last-Event-ID 头，是不可信输入。"""
    with pytest.raises(InvalidEventIdError):
        await log.read("run-1", after=cursor)


# ------------------------------------------------------------------ 上限
async def test_the_log_keeps_only_the_most_recent_events(live_cache: Redis) -> None:
    log = EventLog(live_cache, max_length=3)

    for index in range(10):
        await log.append(token(str(index)))

    assert [one.event.data.text for one in await log.read("run-1")] == ["7", "8", "9"]  # type: ignore[union-attr]


async def test_trimming_is_warned_because_a_reconnect_could_miss_events(
    live_cache: Redis, caplog: pytest.LogCaptureFixture
) -> None:
    log = EventLog(live_cache, max_length=2)
    await log.append(token("一"))
    await log.append(token("二"))

    with caplog.at_level("WARNING"):
        await log.append(token("三"))

    assert caplog.records


async def test_the_cap_applies_per_run(live_cache: Redis) -> None:
    log = EventLog(live_cache, max_length=2)

    for index in range(5):
        await log.append(token(str(index), run_id="run-1"))
    await log.append(token("only", run_id="run-2"))

    assert len(await log.read("run-1")) == 2
    assert len(await log.read("run-2")) == 1


# ------------------------------------------------------------------ follow
async def test_follow_replays_history_before_waiting_for_new_events(log: EventLog) -> None:
    await log.append(token("一"))
    await log.append(finished())

    received = [one.event.model_dump()["type"] async for one in log.follow("run-1")]

    assert received == ["token", "run.finished"]


async def test_follow_stops_at_the_terminal_event(log: EventLog) -> None:
    """SSE 端点靠这个收尾，否则连接会永远挂着。"""
    await log.append(finished())
    await log.append(token("终态之后不该再有事件，但真有也不能让 follow 卡住"))

    received = [one async for one in log.follow("run-1")]

    assert [one.event.type for one in received] == [EventType.RUN_FINISHED]


async def test_follow_stops_when_the_run_fails(log: EventLog) -> None:
    await log.append(failed())

    received = [one async for one in log.follow("run-1")]

    assert [one.event.type for one in received] == [EventType.RUN_FAILED]


async def test_follow_delivers_events_appended_after_it_started(log: EventLog) -> None:
    async def produce() -> None:
        for index in range(3):
            await asyncio.sleep(0)
            await log.append(token(str(index)))
        await log.append(finished())

    task = asyncio.create_task(produce())
    received = [one.event.model_dump()["type"] async for one in log.follow("run-1")]
    await task

    assert received == ["token", "token", "token", "run.finished"]


async def test_follow_resumes_from_a_cursor_without_duplicating(log: EventLog) -> None:
    first = await log.append(token("一"))

    async def produce() -> None:
        await asyncio.sleep(0)
        await log.append(token("二"))
        await log.append(finished())

    task = asyncio.create_task(produce())
    received = [one async for one in log.follow("run-1", after=first.id)]
    await task

    assert received[0].id != first.id
    assert len(received) == 2


async def test_two_followers_of_one_run_both_get_everything(log: EventLog) -> None:
    """一个 run 可能被多个浏览器标签页同时订阅。"""

    async def collect() -> list[str]:
        return [one.id async for one in log.follow("run-1")]

    async def produce() -> None:
        await asyncio.sleep(0)
        await log.append(token("一"))
        await log.append(finished())

    task = asyncio.create_task(produce())
    first, second = await asyncio.gather(collect(), collect())
    await task

    assert first == second
    assert len(first) == 2


async def test_follow_wakes_up_without_polling(log: EventLog) -> None:
    """靠轮询也能过前面的用例，但会让 SSE 的延迟取决于轮询间隔。"""

    async def produce() -> None:
        await asyncio.sleep(0.01)
        await log.append(finished())

    task = asyncio.create_task(produce())
    started = asyncio.get_running_loop().time()
    received = [one async for one in log.follow("run-1")]
    elapsed = asyncio.get_running_loop().time() - started
    await task

    assert len(received) == 1
    assert elapsed < 0.1


async def test_following_a_finished_run_from_its_last_id_returns_at_once(log: EventLog) -> None:
    """跑完之后再订阅、且游标已在末尾 —— 这个 run 不会再有事件了，等下去就是永远挂着。"""
    last = await log.append(finished())

    started = asyncio.get_running_loop().time()
    received = [one async for one in log.follow("run-1", after=last.id)]
    elapsed = asyncio.get_running_loop().time() - started

    assert received == []
    # 「立刻」是这条用例的全部要求：先判终态再阻塞，而不是先阻塞一轮再判
    assert elapsed < 0.1


async def test_following_a_finished_run_from_the_middle_replays_the_rest(log: EventLog) -> None:
    first = await log.append(token("一"))
    await log.append(token("二"))
    await log.append(finished())

    received = [one.event.model_dump()["type"] async for one in log.follow("run-1", after=first.id)]

    assert received == ["token", "run.finished"]


async def test_following_a_failed_run_from_its_last_id_returns_at_once(log: EventLog) -> None:
    last = await log.append(failed())

    assert [one async for one in log.follow("run-1", after=last.id)] == []


# ------------------------------------------------------------------ 跨进程
async def test_events_survive_a_new_log_instance(live_cache: Redis) -> None:
    """换一个 EventLog 实例就是换一个进程 —— 已产生的事件必须还读得到。

    这是内存实现验不了的那条：它重建之后什么都不剩。
    """
    first = EventLog(live_cache)
    await first.append(token("一"))
    await first.append(finished())

    received = [one.event.model_dump()["type"] async for one in EventLog(live_cache).follow("run-1")]

    assert received == ["token", "run.finished"]
