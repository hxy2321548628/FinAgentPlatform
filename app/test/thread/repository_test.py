"""会话读写的测试，连真 Postgres。

**每条用例都要验一遍「别人的看不到」** —— 隔离长在这一层，端点那里一句鉴权判断都没有，
这里漏一个过滤条件就是一个越权入口。
"""

import asyncio
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel.ext.asyncio.session import AsyncSession

from cursor import CursorError
from test.conftest import FAKE_HASH
from thread.model import ThreadRecord
from thread.repository import ThreadRepository
from user.model import UserRole
from user.repository import User, UserRepository


@pytest.fixture
def threads(live_engine: AsyncEngine) -> ThreadRepository:
    return ThreadRepository(live_engine)


@pytest.fixture
async def stranger(live_engine: AsyncEngine) -> User:
    """另一个账号。越权那几条用它，而不是编一个不存在的 uuid。"""
    return await UserRepository(live_engine).create(
        name=f"stranger-{uuid4().hex[:8]}", password_hash=FAKE_HASH, role=UserRole.TEACHER
    )


async def _row(engine: AsyncEngine, thread_id: str) -> ThreadRecord | None:
    """直接看库里那一行。软删除与硬删的区别只有在这个层面才看得出来。"""
    async with AsyncSession(engine) as session:
        return await session.get(ThreadRecord, UUID(thread_id))


# ------------------------------------------------------------------ 列表
async def test_the_list_gives_the_newest_first(threads: ThreadRepository, owner: User) -> None:
    """侧边栏最上面该是刚用过的那个。"""
    first = await threads.create(user_id=owner.id)
    second = await threads.create(user_id=owner.id)

    page = await threads.list(user_id=owner.id, limit=10)

    assert [one.id for one in page.items] == [second.id, first.id]


async def test_a_touched_thread_climbs_back_to_the_top(threads: ThreadRepository, owner: User) -> None:
    """列表按最后活动排，而不是按建立时间 —— 否则老会话再问一句也沉在底下。"""
    first = await threads.create(user_id=owner.id)
    await threads.create(user_id=owner.id)
    await threads.touch(first.id, user_id=owner.id)

    page = await threads.list(user_id=owner.id, limit=10)

    assert page.items[0].id == first.id


async def test_the_list_does_not_show_other_peoples_threads(
    threads: ThreadRepository, owner: User, stranger: User
) -> None:
    await threads.create(user_id=stranger.id)
    mine = await threads.create(user_id=owner.id)

    page = await threads.list(user_id=owner.id, limit=10)

    assert [one.id for one in page.items] == [mine.id]


async def test_the_cursor_walks_the_whole_list_without_repeating(threads: ThreadRepository, owner: User) -> None:
    created = [(await threads.create(user_id=owner.id)).id for _ in range(5)]

    seen: list[str] = []
    cursor: str | None = None
    while True:
        page = await threads.list(user_id=owner.id, cursor=cursor, limit=2)
        seen.extend(one.id for one in page.items)
        cursor = page.next_cursor
        if cursor is None:
            break

    assert seen == list(reversed(created))


async def test_a_full_last_page_still_ends(threads: ThreadRepository, owner: User) -> None:
    """条数正好是页长的整数倍时，最后一页的游标必须是空的，否则前端一直「加载更多」。"""
    for _ in range(2):
        await threads.create(user_id=owner.id)

    page = await threads.list(user_id=owner.id, limit=2)

    assert len(page.items) == 2
    assert page.next_cursor is None


async def test_threads_created_in_the_same_moment_do_not_shadow_each_other(
    threads: ThreadRepository, owner: User
) -> None:
    """游标只带时间的话，同一微秒建出来的两条会在翻页边界上互相顶掉。"""
    created = await asyncio.gather(*(threads.create(user_id=owner.id) for _ in range(4)))

    seen: list[str] = []
    cursor: str | None = None
    while True:
        page = await threads.list(user_id=owner.id, cursor=cursor, limit=1)
        seen.extend(one.id for one in page.items)
        cursor = page.next_cursor
        if cursor is None:
            break

    assert sorted(seen) == sorted(one.id for one in created)


async def test_a_garbage_cursor_is_rejected(threads: ThreadRepository, owner: User) -> None:
    with pytest.raises(CursorError):
        await threads.list(user_id=owner.id, cursor="不是游标", limit=10)


# ------------------------------------------------------------------ 改
async def test_the_title_can_be_changed(threads: ThreadRepository, owner: User) -> None:
    created = await threads.create(user_id=owner.id)

    changed = await threads.update(created.id, user_id=owner.id, title="波动率分析")

    assert changed is not None
    assert changed.title == "波动率分析"


async def test_changing_the_title_leaves_the_agent_config_alone(threads: ThreadRepository, owner: User) -> None:
    """两个字段是分别可选的 —— 只改标题不该把配置清空。"""
    created = await threads.create(user_id=owner.id)
    await threads.update(created.id, user_id=owner.id, agent_config={"model": "aux"})

    changed = await threads.update(created.id, user_id=owner.id, title="只改标题")

    assert changed is not None
    assert changed.agent_config == {"model": "aux"}


async def test_someone_elses_thread_cannot_be_renamed(threads: ThreadRepository, owner: User, stranger: User) -> None:
    created = await threads.create(user_id=stranger.id)

    assert await threads.update(created.id, user_id=owner.id, title="改成我的") is None


async def test_renaming_bumps_the_thread_up_the_list(threads: ThreadRepository, owner: User) -> None:
    """改标题也是一次活动。不动 updated_at 的话，刚改过名的会话仍旧沉在底下。"""
    first = await threads.create(user_id=owner.id)
    await threads.create(user_id=owner.id)

    await threads.update(first.id, user_id=owner.id, title="改过名的")

    page = await threads.list(user_id=owner.id, limit=10)
    assert page.items[0].id == first.id


# ------------------------------------------------------------------ 删
async def test_a_deleted_thread_is_gone_from_the_list(threads: ThreadRepository, owner: User) -> None:
    created = await threads.create(user_id=owner.id)

    assert await threads.delete(created.id, user_id=owner.id) is True

    page = await threads.list(user_id=owner.id, limit=10)
    assert created.id not in [one.id for one in page.items]


async def test_a_deleted_thread_is_not_found(threads: ThreadRepository, owner: User) -> None:
    """删掉之后再查是 404，与从没建过是同一个回答。"""
    created = await threads.create(user_id=owner.id)
    await threads.delete(created.id, user_id=owner.id)

    assert await threads.get(created.id, user_id=owner.id) is None


async def test_deleting_twice_is_not_an_error_the_second_time(threads: ThreadRepository, owner: User) -> None:
    """连点两下删除不该弹红框，第二下只是什么都没做。"""
    created = await threads.create(user_id=owner.id)
    await threads.delete(created.id, user_id=owner.id)

    assert await threads.delete(created.id, user_id=owner.id) is False


async def test_someone_elses_thread_cannot_be_deleted(threads: ThreadRepository, owner: User, stranger: User) -> None:
    created = await threads.create(user_id=stranger.id)

    assert await threads.delete(created.id, user_id=owner.id) is False
    assert await threads.get(created.id, user_id=stranger.id) is not None


async def test_a_deleted_thread_keeps_its_row(threads: ThreadRepository, owner: User, live_engine: AsyncEngine) -> None:
    """软删除：`runs.thread_id` 的外键指着这一行，行没了成本账本就跟着塌一块。"""
    created = await threads.create(user_id=owner.id)
    await threads.delete(created.id, user_id=owner.id)

    row = await _row(live_engine, created.id)
    assert row is not None
    assert row.deleted_at is not None


async def test_purging_really_removes_the_row(threads: ThreadRepository, owner: User, live_engine: AsyncEngine) -> None:
    """建目录失败时的回滚走的是硬删 —— 那一行刚建出来，还没有任何 run 指着它。"""
    created = await threads.create(user_id=owner.id)

    await threads.purge(created.id, user_id=owner.id)

    assert await _row(live_engine, created.id) is None
