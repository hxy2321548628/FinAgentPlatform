"""`artifacts` 表读写的测试，连真库。

产物的身份从「哪个会话的哪个文件」换成表主键，这张表就是新的真相源 ——
因此这里验的是「写下去的能按 run 查回来」，而不是「调用了 session.add」。
"""

from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from artifact.model import CollectedArtifact
from artifact.repository import ArtifactRepository
from run.repository import RunRepository
from thread.repository import Thread
from user.repository import User

PNG_MIME = "image/png"


def a_stored(name: str = "chart.png", size: int = 8) -> CollectedArtifact:
    return CollectedArtifact(
        path=f"t-1/{name}",
        mime=PNG_MIME,
        size=size,
        s3_key=f"tenant/u-1/thread/t-1/{name}",
    )


@pytest.fixture
async def run_id(live_engine: AsyncEngine, owner: User, owned_thread: Thread) -> str:
    """一个真的 run 行。`artifacts.run_id` 有外键，编一个 uuid 写不进去。"""
    identifier = uuid4().hex
    await RunRepository(live_engine).create(run_id=identifier, thread_id=owned_thread.id, user_id=owner.id)
    return identifier


async def test_added_artifacts_come_back_with_ids(live_engine: AsyncEngine, run_id: str) -> None:
    repository = ArtifactRepository(live_engine)

    added = await repository.add(run_id, [a_stored()])

    assert len(added) == 1
    assert added[0].s3_key == "tenant/u-1/thread/t-1/chart.png"
    assert added[0].id


async def test_each_artifact_gets_its_own_id(live_engine: AsyncEngine, run_id: str) -> None:
    repository = ArtifactRepository(live_engine)

    added = await repository.add(run_id, [a_stored("one.png"), a_stored("two.png")])

    assert len({one.id for one in added}) == 2


async def test_artifacts_are_listed_by_run(live_engine: AsyncEngine, run_id: str) -> None:
    repository = ArtifactRepository(live_engine)
    await repository.add(run_id, [a_stored("one.png"), a_stored("two.png")])

    found = await repository.list(run_id)

    assert sorted(one.s3_key for one in found) == [
        "tenant/u-1/thread/t-1/one.png",
        "tenant/u-1/thread/t-1/two.png",
    ]


async def test_another_runs_artifacts_are_not_listed(live_engine: AsyncEngine, run_id: str) -> None:
    repository = ArtifactRepository(live_engine)
    await repository.add(run_id, [a_stored()])

    assert await repository.list(uuid4().hex) == []


async def test_adding_nothing_writes_nothing(live_engine: AsyncEngine, run_id: str) -> None:
    """跑完什么都没画出来是正常的，不该因此炸在插入上。"""
    repository = ArtifactRepository(live_engine)

    assert await repository.add(run_id, []) == []
    assert await repository.list(run_id) == []


async def test_an_artifact_that_never_reached_the_object_store_is_not_written(
    live_engine: AsyncEngine, run_id: str
) -> None:
    """表里的每一行都必须指向一个真的对象，否则查出来的 s3_key 下载不了。"""
    repository = ArtifactRepository(live_engine)
    unstored = CollectedArtifact(path="t-1/chart.png", mime=PNG_MIME, size=8)

    assert await repository.add(run_id, [unstored]) == []
    assert await repository.list(run_id) == []


async def test_the_uploaded_ones_are_written_even_when_a_sibling_failed(live_engine: AsyncEngine, run_id: str) -> None:
    """一张图传失败不该连累另一张 —— 那次分析已经跑完了。"""
    repository = ArtifactRepository(live_engine)
    unstored = CollectedArtifact(path="t-1/two.png", mime=PNG_MIME, size=8)

    added = await repository.add(run_id, [a_stored("one.png"), unstored])

    assert [one.s3_key for one in added] == ["tenant/u-1/thread/t-1/one.png"]


async def test_an_artifact_of_an_unknown_run_is_refused(live_engine: AsyncEngine) -> None:
    """外键挡住无主的产物 —— 没有 run 的产物没人能查到，也没人会去删。"""
    repository = ArtifactRepository(live_engine)

    with pytest.raises(IntegrityError):
        await repository.add(uuid4().hex, [a_stored()])


async def test_a_large_artifact_size_survives(live_engine: AsyncEngine, run_id: str) -> None:
    """`size` 是 bigint。用 int 列的话超过 2GB 的产物会在插入时炸，而那时 run 已经跑完了。"""
    huge = 5 * 1024**3
    repository = ArtifactRepository(live_engine)

    added = await repository.add(run_id, [a_stored(size=huge)])

    assert added[0].size == huge
