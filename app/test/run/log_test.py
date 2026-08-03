import asyncio

import pytest

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


# ------------------------------------------------------------------ 追加与 id
def test_append_returns_a_redis_stream_shaped_id() -> None:
    log = EventLog()

    logged = log.append(token("你"))

    millisecond, _, sequence = logged.id.partition("-")
    assert millisecond.isdigit()
    assert sequence.isdigit()


def test_ids_increase_monotonically_within_one_run() -> None:
    log = EventLog()

    ids = [log.append(token(str(index))).id for index in range(50)]

    assert ids == sorted(ids, key=lambda one: tuple(int(part) for part in one.split("-")))
    assert len(set(ids)) == len(ids)


def test_ids_stay_unique_when_events_land_in_the_same_millisecond() -> None:
    """毫秒精度不够分辨相邻事件，序号那一段就是为此存在的。"""
    log = EventLog()

    ids = [log.append(token(str(index))).id for index in range(200)]
    milliseconds = {one.split("-")[0] for one in ids}

    assert len(milliseconds) < len(ids)
    assert len(set(ids)) == len(ids)


def test_ids_are_allocated_per_run_not_globally() -> None:
    """两个 run 的事件流互不相干，各自从头编号。"""
    log = EventLog()

    log.append(token("a", run_id="run-1"))
    log.append(token("b", run_id="run-2"))

    assert [one.event.data.text for one in log.read("run-1")] == ["a"]  # type: ignore[union-attr]
    assert [one.event.data.text for one in log.read("run-2")] == ["b"]  # type: ignore[union-attr]


# ------------------------------------------------------------------ 读取与重放
def test_read_without_cursor_returns_the_whole_run() -> None:
    log = EventLog()
    log.append(token("一"))
    log.append(token("二"))

    assert len(log.read("run-1")) == 2


def test_read_after_a_cursor_skips_what_the_client_already_has() -> None:
    log = EventLog()
    first = log.append(token("一"))
    log.append(token("二"))
    log.append(token("三"))

    replayed = log.read("run-1", after=first.id)

    assert [one.event.data.text for one in replayed] == ["二", "三"]  # type: ignore[union-attr]


def test_replay_from_any_id_loses_nothing_and_repeats_nothing() -> None:
    """断线重连的核心保证：每个位置断开，补齐的部分与已收到的部分严丝合缝。"""
    log = EventLog()
    logged = [log.append(token(str(index))) for index in range(20)]

    for cut in range(len(logged)):
        received = logged[: cut + 1]
        replayed = log.read("run-1", after=received[-1].id)

        assert [one.id for one in received] + [one.id for one in replayed] == [one.id for one in logged]


def test_read_after_the_last_id_returns_nothing() -> None:
    log = EventLog()
    last = log.append(token("一"))

    assert log.read("run-1", after=last.id) == []


def test_read_of_an_unknown_run_returns_nothing() -> None:
    log = EventLog()

    assert log.read("never-existed") == []


def test_cursor_ordering_is_numeric_not_lexicographic() -> None:
    """`10-0` 字符串比较小于 `9-0`，直接比字符串会把整段历史当成未读重发。"""
    log = EventLog()

    assert log.read("run-1", after="9-0") == []
    log.append(token("一"))
    assert log.read("run-1", after="99999999999999-0") == []


@pytest.mark.parametrize("cursor", ["", "abc", "1-", "-0", "1-2-3", "x-y", "1.5-0"])
def test_a_malformed_cursor_is_rejected(cursor: str) -> None:
    """游标来自客户端的 Last-Event-ID 头，是不可信输入。"""
    log = EventLog()

    with pytest.raises(InvalidEventIdError):
        log.read("run-1", after=cursor)


# ------------------------------------------------------------------ 上限
def test_the_log_keeps_only_the_most_recent_events() -> None:
    log = EventLog(max_length=3)

    for index in range(10):
        log.append(token(str(index)))

    assert [one.event.data.text for one in log.read("run-1")] == ["7", "8", "9"]  # type: ignore[union-attr]


def test_trimming_is_warned_because_a_reconnect_could_miss_events(caplog: pytest.LogCaptureFixture) -> None:
    log = EventLog(max_length=2)
    log.append(token("一"))
    log.append(token("二"))

    with caplog.at_level("WARNING"):
        log.append(token("三"))

    assert caplog.records


def test_the_cap_applies_per_run() -> None:
    log = EventLog(max_length=2)

    for index in range(5):
        log.append(token(str(index), run_id="run-1"))
    log.append(token("only", run_id="run-2"))

    assert len(log.read("run-1")) == 2
    assert len(log.read("run-2")) == 1


def test_the_oldest_run_is_dropped_once_too_many_runs_pile_up() -> None:
    """进程长跑时 run 只增不减，没有这条上限内存就是无界增长。"""
    log = EventLog(max_run=2)

    log.append(token("一", run_id="run-1"))
    log.append(token("二", run_id="run-2"))
    log.append(token("三", run_id="run-3"))

    assert log.read("run-1") == []
    assert len(log.read("run-2")) == 1
    assert len(log.read("run-3")) == 1


# ------------------------------------------------------------------ follow
async def test_follow_replays_history_before_waiting_for_new_events() -> None:
    log = EventLog()
    log.append(token("一"))
    log.append(finished())

    received = [one.event.model_dump()["type"] async for one in log.follow("run-1")]

    assert received == ["token", "run.finished"]


async def test_follow_stops_at_the_terminal_event() -> None:
    """SSE 端点靠这个收尾，否则连接会永远挂着。"""
    log = EventLog()
    log.append(finished())
    log.append(token("终态之后不该再有事件，但真有也不能让 follow 卡住"))

    received = [one async for one in log.follow("run-1")]

    assert [one.event.type for one in received] == [EventType.RUN_FINISHED]


async def test_follow_stops_when_the_run_fails() -> None:
    log = EventLog()
    log.append(failed())

    received = [one async for one in log.follow("run-1")]

    assert [one.event.type for one in received] == [EventType.RUN_FAILED]


async def test_follow_delivers_events_appended_after_it_started() -> None:
    log = EventLog()

    async def produce() -> None:
        for index in range(3):
            await asyncio.sleep(0)
            log.append(token(str(index)))
        log.append(finished())

    task = asyncio.create_task(produce())
    received = [one async for one in log.follow("run-1")]
    await task

    assert [one.event.model_dump()["type"] for one in received] == ["token", "token", "token", "run.finished"]


async def test_follow_resumes_from_a_cursor_without_duplicating() -> None:
    log = EventLog()
    first = log.append(token("一"))

    async def produce() -> None:
        await asyncio.sleep(0)
        log.append(token("二"))
        log.append(finished())

    task = asyncio.create_task(produce())
    received = [one async for one in log.follow("run-1", after=first.id)]
    await task

    assert received[0].id != first.id
    assert len(received) == 2


async def test_two_followers_of_one_run_both_get_everything() -> None:
    """一个 run 可能被多个浏览器标签页同时订阅。"""
    log = EventLog()

    async def collect() -> list[str]:
        return [one.id async for one in log.follow("run-1")]

    async def produce() -> None:
        await asyncio.sleep(0)
        log.append(token("一"))
        log.append(finished())

    task = asyncio.create_task(produce())
    first, second = await asyncio.gather(collect(), collect())
    await task

    assert first == second
    assert len(first) == 2


async def test_follow_wakes_up_without_polling() -> None:
    """靠轮询也能过前面的用例，但会让 SSE 的延迟取决于轮询间隔。"""
    log = EventLog()

    async def produce() -> None:
        await asyncio.sleep(0.01)
        log.append(finished())

    task = asyncio.create_task(produce())
    started = asyncio.get_running_loop().time()
    received = [one async for one in log.follow("run-1")]
    elapsed = asyncio.get_running_loop().time() - started
    await task

    assert len(received) == 1
    assert elapsed < 0.1


async def test_following_a_finished_run_from_its_last_id_returns_at_once() -> None:
    """跑完之后再订阅、且游标已在末尾 —— 这个 run 不会再有事件了，等下去就是永远挂着。"""
    log = EventLog()
    last = log.append(finished())

    received = [one async for one in log.follow("run-1", after=last.id)]

    assert received == []


async def test_following_a_finished_run_from_the_middle_replays_the_rest() -> None:
    log = EventLog()
    first = log.append(token("一"))
    log.append(token("二"))
    log.append(finished())

    received = [one async for one in log.follow("run-1", after=first.id)]

    assert [one.event.model_dump()["type"] for one in received] == ["token", "run.finished"]


async def test_following_a_failed_run_from_its_last_id_returns_at_once() -> None:
    log = EventLog()
    last = log.append(failed())

    assert [one async for one in log.follow("run-1", after=last.id)] == []
