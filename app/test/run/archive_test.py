"""事件归档的测试，连真 Postgres 与真 Redis。

**这一步的全部意义在第一条用例上**：Stream 裁掉的那段历史，教师翻的时候要能完整看到。
少的那一段不会报错 —— 它只是一段空白，而空白是发现不了的。
"""

from typing import cast
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from event.model import Event, RunFinishedData, RunFinishedEvent, TokenData, TokenEvent
from run.archive import EventArchive, pack, unpack
from run.log import EventLog, stream_key
from store.redis import StreamEntry


def token(text: str, run_id: str) -> Event:
    return TokenEvent(ts=1, run_id=run_id, path=(), data=TokenData(text=text))


def finished(run_id: str) -> Event:
    return RunFinishedEvent(ts=1, run_id=run_id, path=(), data=RunFinishedData())


@pytest.fixture
def archive(live_engine: AsyncEngine) -> EventArchive:
    return EventArchive(live_engine)


@pytest.fixture
def run_id() -> str:
    return uuid4().hex


# ------------------------------------------------------------------ id 打包
def test_a_packed_id_survives_the_round_trip() -> None:
    """还原不出原样的 id，`Last-Event-ID` 就对不上，重连会重发或漏发。"""
    assert unpack(pack("1753948800123-7")) == "1753948800123-7"


def test_packed_ids_sort_the_same_way_the_originals_do() -> None:
    """`10-0` 字符串比较小于 `9-0`，打包就是为了让数据库能按发生顺序排。"""
    assert pack("9-0") < pack("10-0")
    assert pack("1753948800123-1") < pack("1753948800124-0")


def test_a_packed_id_stays_inside_bigint() -> None:
    """溢出 bigint 会让写入直接失败。上界要留到这套系统不可能还在跑的年份。

    7256476800000 毫秒是公元 2200 年，同毫秒内序号取满 20 位。
    """
    assert pack("7256476800000-1048575") < 2**63


# ------------------------------------------------------------------ 归档与重放
async def test_appending_an_event_archives_it(live_cache: Redis, archive: EventArchive, run_id: str) -> None:
    log = EventLog(live_cache, archive=archive)

    logged = await log.append(token("你", run_id))

    replayed = await archive.replay(run_id)
    assert [one.id for one in replayed] == [logged.id]


async def test_history_trimmed_out_of_the_stream_is_still_replayed(
    live_cache: Redis, archive: EventArchive, run_id: str
) -> None:
    """步骤五的验证①：Stream 与 Postgres 之间只要有一点缝，教师就会看到一段空白。"""
    log = EventLog(live_cache, archive=archive, max_length=3)
    written = [await log.append(token(str(index), run_id)) for index in range(10)]

    assert len(cast(list[StreamEntry], await live_cache.xrange(stream_key(run_id)))) == 3
    assert [one.id for one in await log.read(run_id)] == [one.id for one in written]


async def test_a_stream_that_expired_entirely_still_replays(
    live_cache: Redis, archive: EventArchive, run_id: str
) -> None:
    """TTL 到点之后 Stream 整条消失。翻几个月前的会话走的就是这条路径。"""
    log = EventLog(live_cache, archive=archive)
    written = [await log.append(token(str(index), run_id)) for index in range(3)]
    await live_cache.delete(stream_key(run_id))

    assert [one.id for one in await log.read(run_id)] == [one.id for one in written]


async def test_replay_does_not_duplicate_what_the_stream_still_has(
    live_cache: Redis, archive: EventArchive, run_id: str
) -> None:
    """归档与 Stream 是重叠的，不划清界限就会把同一条事件推两遍。"""
    log = EventLog(live_cache, archive=archive)
    for index in range(5):
        await log.append(token(str(index), run_id))

    replayed = await log.read(run_id)

    assert len(replayed) == 5
    assert len({one.id for one in replayed}) == 5


async def test_a_cursor_still_works_across_the_seam(live_cache: Redis, archive: EventArchive, run_id: str) -> None:
    """断线重连的游标可能正好落在被裁掉的那一段里。"""
    log = EventLog(live_cache, archive=archive, max_length=3)
    written = [await log.append(token(str(index), run_id)) for index in range(10)]

    resumed = await log.read(run_id, after=written[1].id)

    assert [one.id for one in resumed] == [one.id for one in written[2:]]


async def test_following_a_run_whose_stream_expired_ends_instead_of_hanging(
    live_cache: Redis, archive: EventArchive, run_id: str
) -> None:
    """Stream 没了之后，「这个 run 结束了没有」只能问归档 —— 不问就是永远挂着。"""
    log = EventLog(live_cache, archive=archive)
    await log.append(token("一", run_id))
    await log.append(finished(run_id))
    await live_cache.delete(stream_key(run_id))

    received = [one.event.model_dump()["type"] async for one in log.follow(run_id)]

    assert received == ["token", "run.finished"]


async def test_recording_the_same_event_twice_is_harmless(
    archive: EventArchive, live_cache: Redis, run_id: str
) -> None:
    """补归档与重投的 run 都会撞上主键。撞上就得当无事发生，不能把 run 掀掉。"""
    log = EventLog(live_cache, archive=archive)
    logged = await log.append(token("一", run_id))

    await archive.record(logged)

    assert len(await archive.replay(run_id)) == 1


async def test_an_archive_failure_does_not_break_the_run(
    live_cache: Redis, archive: EventArchive, caplog: pytest.LogCaptureFixture
) -> None:
    """归档挂了，教师拿到的分析结果仍然是对的 —— 只是这段历史以后翻不到。"""
    log = EventLog(live_cache, archive=archive)

    with caplog.at_level("ERROR"):
        logged = await log.append(token("一", "not-a-uuid"))

    assert logged.id
    assert caplog.records
