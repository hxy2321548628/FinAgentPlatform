"""Broker 侧 Skill 字节仓库与 workspace 全量对齐。"""

import logging
from pathlib import Path

import pytest

from broker.skill import SkillFile, SkillReference, SkillStore
from sandbox.workspace import Workspace

SKILL_ID = "11111111-1111-1111-1111-111111111111"
SKILL_NAME = "annualized-naming"
VERSION = 1
SKILL_MD = b"---\nname: annualized-naming\ndescription: annualized naming\n---\n"


def _stored(store: SkillStore) -> None:
    store.save_version(
        SKILL_ID,
        VERSION,
        (
            SkillFile(path="SKILL.md", content=SKILL_MD),
            SkillFile(path="notes/rule.txt", content=b"252 trading days"),
        ),
    )


def _reference() -> tuple[SkillReference, ...]:
    return (SkillReference(skill_id=SKILL_ID, version=VERSION, name=SKILL_NAME),)


def test_a_version_is_saved_under_skill_id_and_version(tmp_path: Path) -> None:
    store = SkillStore(tmp_path / "catalog")

    _stored(store)

    root = tmp_path / "catalog" / SKILL_ID / str(VERSION)
    assert (root / "SKILL.md").read_bytes() == SKILL_MD
    assert (root / "notes" / "rule.txt").read_bytes() == b"252 trading days"


@pytest.mark.parametrize("path", ["../outside.txt", "/etc/passwd", "notes/../../outside.txt"])
def test_a_stored_path_cannot_escape_the_version_directory(tmp_path: Path, path: str) -> None:
    store = SkillStore(tmp_path / "catalog")

    with pytest.raises(ValueError, match="路径"):
        store.save_version(SKILL_ID, VERSION, (SkillFile(path=path, content=b"x"),))


def test_align_copies_every_missing_file_into_the_plain_skill_directory(tmp_path: Path) -> None:
    store = SkillStore(tmp_path / "catalog")
    workspace = Workspace(tmp_path / "workspace")
    thread_id = workspace.create("thread-1")
    _stored(store)

    store.align(workspace.path(thread_id), _reference())

    target = workspace.path(thread_id) / "skill" / SKILL_NAME
    assert (target / "SKILL.md").read_bytes() == SKILL_MD
    assert (target / "notes" / "rule.txt").read_bytes() == b"252 trading days"


def test_align_restores_changed_content_and_warns(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    store = SkillStore(tmp_path / "catalog")
    workspace = Workspace(tmp_path / "workspace")
    thread_id = workspace.create("thread-1")
    _stored(store)
    store.align(workspace.path(thread_id), _reference())
    changed = workspace.path(thread_id) / "skill" / SKILL_NAME / "SKILL.md"
    changed.write_bytes(b"broken")

    with caplog.at_level(logging.WARNING, logger="broker.skill"):
        store.align(workspace.path(thread_id), _reference())

    assert changed.read_bytes() == SKILL_MD
    assert any("覆盖" in one.message and "SKILL.md" in one.message for one in caplog.records)


def test_align_deletes_every_unlisted_file_and_directory_and_warns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    store = SkillStore(tmp_path / "catalog")
    workspace = Workspace(tmp_path / "workspace")
    thread_id = workspace.create("thread-1")
    _stored(store)
    store.align(workspace.path(thread_id), _reference())
    extra = workspace.path(thread_id) / "skill" / "invented" / "nested" / "extra.txt"
    extra.parent.mkdir(parents=True)
    extra.write_bytes(b"extra")

    with caplog.at_level(logging.WARNING, logger="broker.skill"):
        store.align(workspace.path(thread_id), _reference())

    assert not (workspace.path(thread_id) / "skill" / "invented").exists()
    assert any("删除" in one.message and "invented" in one.message for one in caplog.records)


def test_align_does_not_rewrite_an_unchanged_file(tmp_path: Path) -> None:
    store = SkillStore(tmp_path / "catalog")
    workspace = Workspace(tmp_path / "workspace")
    thread_id = workspace.create("thread-1")
    _stored(store)
    store.align(workspace.path(thread_id), _reference())
    target = workspace.path(thread_id) / "skill" / SKILL_NAME / "SKILL.md"
    before = target.stat().st_mtime_ns

    store.align(workspace.path(thread_id), _reference())

    assert target.stat().st_mtime_ns == before


def test_align_fails_closed_when_a_stored_version_is_missing(tmp_path: Path) -> None:
    store = SkillStore(tmp_path / "catalog")
    workspace = Workspace(tmp_path / "workspace")
    thread_id = workspace.create("thread-1")

    with pytest.raises(FileNotFoundError):
        store.align(workspace.path(thread_id), _reference())


def test_list_version_returns_recursive_file_metadata(tmp_path: Path) -> None:
    store = SkillStore(tmp_path / "catalog")
    _stored(store)

    assert [(one.path, one.size) for one in store.list_version(SKILL_ID, VERSION)] == [
        ("SKILL.md", len(SKILL_MD)),
        ("notes/rule.txt", len(b"252 trading days")),
    ]


def test_read_version_file_returns_bytes_and_rejects_escape(tmp_path: Path) -> None:
    store = SkillStore(tmp_path / "catalog")
    _stored(store)

    assert store.read_version_file(SKILL_ID, VERSION, "notes/rule.txt") == b"252 trading days"
    with pytest.raises(ValueError, match="路径"):
        store.read_version_file(SKILL_ID, VERSION, "../outside.txt")


def test_read_version_file_does_not_follow_symlink(tmp_path: Path) -> None:
    store = SkillStore(tmp_path / "catalog")
    _stored(store)
    root = tmp_path / "catalog" / SKILL_ID / str(VERSION)
    (root / "escape").symlink_to(tmp_path / "outside.txt")

    with pytest.raises(FileNotFoundError, match="文件不存在"):
        store.read_version_file(SKILL_ID, VERSION, "escape")
