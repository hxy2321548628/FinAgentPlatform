import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import pytest
import yaml

from app.memory import store as store_module
from app.memory.store import (
    MAX_MEMORY_CONTENT_CHARACTER,
    MAX_MEMORY_INDEX_BYTE,
    MEMORY_BACKUP_DIR,
    MEMORY_INDEX,
    MEMORY_STAGE_DIR,
    MemoryCapacityError,
    MemoryRecord,
    MemoryStore,
    MemoryStoreError,
    MemoryVersionConflictError,
)
from app.sandbox.path import MEMORY_DIR
from app.sandbox.workspace import Workspace


@pytest.fixture
def space(tmp_path: Path) -> Workspace:
    workspace = Workspace(tmp_path)
    workspace.create("thread-1")
    return workspace


@pytest.fixture
def store(space: Workspace) -> MemoryStore:
    return MemoryStore(space)


def record(slug: str = "project-preference-tabs", *, description: str = "教师偏好使用制表符缩进") -> MemoryRecord:
    return MemoryRecord(
        slug=slug,
        name=slug,
        description=description,
        type="user",
        content="教师偏好使用制表符缩进。",
    )


def test_write_persists_one_markdown_record_with_fixed_frontmatter(store: MemoryStore, space: Workspace) -> None:
    store.write("thread-1", record())

    target = space.lookup("thread-1") / MEMORY_DIR / "project-preference-tabs.md"
    frontmatter, content = target.read_text(encoding="utf-8").removeprefix("---\n").split("\n---\n\n", 1)
    assert yaml.safe_load(frontmatter) == {
        "name": "project-preference-tabs",
        "description": "教师偏好使用制表符缩进",
        "type": "user",
    }
    assert content == "教师偏好使用制表符缩进。\n"


def test_read_round_trips_a_record(store: MemoryStore) -> None:
    expected = record()
    store.write("thread-1", expected)

    assert store.read("thread-1", expected.slug) == expected


def test_list_ignores_the_rebuildable_index_and_sorts_by_slug(store: MemoryStore) -> None:
    store.write("thread-1", record("z-last"))
    store.write("thread-1", record("a-first"))

    assert [one.slug for one in store.list("thread-1")] == ["a-first", "z-last"]


def test_rebuild_index_lists_only_active_record_files(store: MemoryStore, space: Workspace) -> None:
    store.write("thread-1", record("old-item", description="旧记录"))
    store.write("thread-1", record("active-item", description="活动记录"))
    store.delete("thread-1", "old-item")

    memory = space.lookup("thread-1") / MEMORY_DIR
    (memory / MEMORY_INDEX).write_text("伪造的索引\n", encoding="utf-8")
    store.rebuild_index("thread-1")

    index = (memory / MEMORY_INDEX).read_text(encoding="utf-8")
    assert "active-item.md" in index
    assert "old-item.md" not in index
    assert "伪造的索引" not in index


def test_deleting_a_record_also_rebuilds_the_index(store: MemoryStore, space: Workspace) -> None:
    store.write("thread-1", record())

    store.delete("thread-1", "project-preference-tabs")

    memory = space.lookup("thread-1") / MEMORY_DIR
    assert not (memory / "project-preference-tabs.md").exists()
    assert "project-preference-tabs" not in (memory / MEMORY_INDEX).read_text(encoding="utf-8")


@pytest.mark.parametrize("slug", ["../secret", "/absolute", "nested/item", "MEMORY", "", ".hidden"])
def test_an_invalid_or_reserved_slug_is_rejected(store: MemoryStore, slug: str) -> None:
    with pytest.raises(MemoryStoreError):
        store.write("thread-1", record(slug))


def test_a_symbolic_link_record_is_rejected(store: MemoryStore, space: Workspace, tmp_path: Path) -> None:
    memory = space.lookup("thread-1") / MEMORY_DIR
    memory.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("凭据", encoding="utf-8")
    (memory / "linked.md").symlink_to(outside)

    with pytest.raises(MemoryStoreError, match="符号链接"):
        store.read("thread-1", "linked")


def test_malformed_frontmatter_is_rejected_as_a_store_error(store: MemoryStore, space: Workspace) -> None:
    memory = space.lookup("thread-1") / MEMORY_DIR
    memory.mkdir()
    (memory / "broken.md").write_text("---\nname: [\n---\n\n正文\n", encoding="utf-8")

    with pytest.raises(MemoryStoreError, match="frontmatter 无法解析"):
        store.read("thread-1", "broken")


def test_reading_an_absent_memdir_does_not_create_it(store: MemoryStore, space: Workspace) -> None:
    assert store.list("thread-1") == []

    assert not (space.lookup("thread-1") / MEMORY_DIR).exists()


def test_an_unknown_thread_is_not_created_by_a_memory_read(tmp_path: Path) -> None:
    store = MemoryStore(Workspace(tmp_path))

    with pytest.raises(FileNotFoundError):
        store.list("deleted-thread")

    assert not (tmp_path / "deleted-thread").exists()


def test_concurrent_writes_to_one_thread_do_not_lose_index_entries(store: MemoryStore, space: Workspace) -> None:
    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda index: store.write("thread-1", record(f"item-{index}")), range(20)))

    memory = space.lookup("thread-1") / MEMORY_DIR
    index = (memory / MEMORY_INDEX).read_text(encoding="utf-8")
    assert [one.slug for one in store.list("thread-1")] == sorted(f"item-{index}" for index in range(20))
    assert all(index.count(f"item-{number}.md") == 1 for number in range(20))
    assert not list(memory.glob("*.tmp"))


def test_export_returns_a_stable_version_and_all_content(store: MemoryStore) -> None:
    store.write("thread-1", record("second"))
    store.write("thread-1", record("first"))

    first = store.export("thread-1")
    second = store.export("thread-1")

    assert first.version == second.version
    assert [one.slug for one in first.records] == ["first", "second"]
    assert all(one.content == "教师偏好使用制表符缩进。" for one in first.records)


def test_replace_is_all_or_nothing_and_removes_records_outside_the_new_set(
    store: MemoryStore, space: Workspace
) -> None:
    store.write("thread-1", record("old-first"))
    store.write("thread-1", record("old-second"))
    before = store.export("thread-1")

    after = store.replace(
        "thread-1",
        (record("new-first"), record("new-second")),
        expected_version=before.version,
    )

    assert after.version != before.version
    assert [one.slug for one in store.list("thread-1")] == ["new-first", "new-second"]
    memory = space.lookup("thread-1") / MEMORY_DIR
    assert not (memory / "old-first.md").exists()
    assert not (memory / "old-second.md").exists()


def test_replace_rejects_a_stale_version_without_changing_any_file(store: MemoryStore, space: Workspace) -> None:
    store.write("thread-1", record("original"))
    before = _memory_bytes(space)

    with pytest.raises(MemoryVersionConflictError):
        store.replace("thread-1", (record("replacement"),), expected_version="stale")

    assert _memory_bytes(space) == before


def test_replace_rejects_duplicate_slugs_before_changing_any_file(store: MemoryStore, space: Workspace) -> None:
    store.write("thread-1", record("original"))
    before = _memory_bytes(space)

    with pytest.raises(MemoryStoreError, match="重复"):
        store.replace("thread-1", (record("duplicate"), record("duplicate")))

    assert _memory_bytes(space) == before


def test_a_failed_directory_swap_restores_the_exact_previous_set(
    store: MemoryStore,
    space: Workspace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store.write("thread-1", record("original"))
    before = _memory_bytes(space)
    real_replace = __import__("os").replace

    def fail_promotion(source: str | Path, destination: str | Path) -> None:
        source_path = Path(source)
        destination_path = Path(destination)
        if source_path.parent.name == MEMORY_STAGE_DIR and destination_path.parent.name == MEMORY_DIR:
            raise OSError("模拟提交失败")
        real_replace(source, destination)

    monkeypatch.setattr("app.memory.store.os.replace", fail_promotion)

    with pytest.raises(OSError, match="模拟提交失败"):
        store.replace("thread-1", (record("replacement"),))

    assert _memory_bytes(space) == before


def test_single_record_content_limit_is_checked_before_write(store: MemoryStore, space: Workspace) -> None:
    before = _memory_bytes(space)
    oversized = record("too-long")
    oversized = MemoryRecord(
        slug=oversized.slug,
        name=oversized.name,
        description=oversized.description,
        type=oversized.type,
        content="字" * (MAX_MEMORY_CONTENT_CHARACTER + 1),
    )

    with pytest.raises(MemoryCapacityError, match="正文"):
        store.write("thread-1", oversized)

    assert _memory_bytes(space) == before


def test_total_serialized_cap_is_checked_against_the_replacement_set(space: Workspace) -> None:
    store = MemoryStore(space, max_byte=600)
    store.write("thread-1", record("original"))
    before = _memory_bytes(space)
    large = MemoryRecord(
        slug="large",
        name="large",
        description="大正文",
        type="user",
        content="x" * 500,
    )

    with pytest.raises(MemoryCapacityError, match="总量"):
        store.write("thread-1", large)

    assert _memory_bytes(space) == before


def test_index_cap_is_checked_before_replacing_the_directory(store: MemoryStore, space: Workspace) -> None:
    store.write("thread-1", record("original"))
    before = _memory_bytes(space)
    huge_description = "索" * MAX_MEMORY_INDEX_BYTE

    with pytest.raises(MemoryCapacityError, match="索引"):
        store.replace("thread-1", (record("huge-index", description=huge_description),))

    assert _memory_bytes(space) == before


def test_replace_staging_stays_inside_the_thread_quota_and_leaves_no_artifacts(
    store: MemoryStore,
    space: Workspace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = space.lookup("thread-1")
    seen: list[Path] = []
    real_write = store_module._write_stage_file

    def observe(target: Path, content: bytes, *, updated_at: datetime | None) -> None:
        seen.append(target.parent)
        real_write(target, content, updated_at=updated_at)

    monkeypatch.setattr(store_module, "_write_stage_file", observe)

    store.replace("thread-1", (record("replacement"),))

    assert seen
    memory = workspace / MEMORY_DIR
    assert memory / MEMORY_STAGE_DIR in seen
    assert set(seen) <= {memory, memory / MEMORY_STAGE_DIR}
    assert not (memory / MEMORY_STAGE_DIR).exists()
    assert not (memory / MEMORY_BACKUP_DIR).exists()


def test_cleanup_failure_after_commit_is_reported_but_the_committed_replace_still_succeeds(
    store: MemoryStore,
    space: Workspace,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    store.write("thread-1", record("original"))
    real_rmtree = shutil.rmtree

    def fail_backup_cleanup(target: str | Path) -> None:
        if Path(target).name == MEMORY_BACKUP_DIR:
            raise OSError("模拟备份清理失败")
        real_rmtree(target)

    monkeypatch.setattr("app.memory.store.shutil.rmtree", fail_backup_cleanup)

    with caplog.at_level("WARNING", logger="app.memory.store"):
        snapshot = store.replace("thread-1", (record("replacement"),))

    assert [one.slug for one in snapshot.records] == ["replacement"]
    assert "清理失败" in caplog.text

    monkeypatch.setattr("app.memory.store.shutil.rmtree", real_rmtree)
    assert [one.slug for one in store.export("thread-1").records] == ["replacement"]
    memory = space.lookup("thread-1") / MEMORY_DIR
    assert not (memory / MEMORY_BACKUP_DIR).exists()


def _memory_bytes(space: Workspace) -> dict[str, bytes]:
    memory = space.lookup("thread-1") / MEMORY_DIR
    if not memory.exists():
        return {}
    return {target.name: target.read_bytes() for target in sorted(memory.iterdir()) if target.is_file()}
