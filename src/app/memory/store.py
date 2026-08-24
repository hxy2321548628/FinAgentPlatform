"""Thread 私有 memdir 的物理存储。

记忆正文只存在 thread workspace 的受保护 ``.memory`` 目录。
本模块负责固定 frontmatter schema、同 thread 串行化和活动文件集事务替换；
``MEMORY.md`` 只是可从活动记录重建的短索引。
"""

from __future__ import annotations

import builtins
import hashlib
import logging
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import yaml

from app.sandbox.path import MEMORY_DIR
from app.sandbox.workspace import Workspace

MEMORY_INDEX: Final = "MEMORY.md"
MEMORY_TYPE: Final = frozenset({"user", "feedback", "project", "reference"})
MEMORY_STAGE_DIR: Final = ".stage"
MEMORY_BACKUP_DIR: Final = ".backup"
MEMORY_PROMOTING_MARKER: Final = ".promoting"
MEMORY_COMMITTED_MARKER: Final = ".committed"
_MEMORY_TRANSACTION_ENTRY: Final = frozenset(
    {MEMORY_STAGE_DIR, MEMORY_BACKUP_DIR, MEMORY_PROMOTING_MARKER, MEMORY_COMMITTED_MARKER}
)
DEFAULT_MEMORY_MAX_BYTE: Final = 1024 * 1024
MAX_MEMORY_CONTENT_CHARACTER: Final = 100_000
MAX_MEMORY_INDEX_BYTE: Final = 64 * 1024
_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_FRONTMATTER_KEY: Final = frozenset({"name", "description", "type"})

logger = logging.getLogger(__name__)


class MemoryStoreError(ValueError):
    """记忆记录的路径、schema 或物理形状不合法。"""


class MemoryCapacityError(MemoryStoreError):
    """替换后的活动记忆集超过显式 soft cap。"""


class MemoryVersionConflictError(MemoryStoreError):
    """调用方基于的版本已经过期，不能覆盖并发更新。"""


@dataclass(frozen=True)
class MemoryRecord:
    """一条 thread 私有记忆。"""

    slug: str
    name: str
    description: str
    type: str
    content: str
    updated_at: datetime | None = field(default=None, compare=False)


@dataclass(frozen=True)
class MemoryStoreSnapshot:
    """同一把 thread 锁内读到的完整活动集及其确定性版本。"""

    records: tuple[MemoryRecord, ...]
    version: str


class MemoryStore:
    """经由 Workspace 管理的 thread memdir。

    Args:
        workspace: workspace 的唯一管理器；锁与会话删除共用它的 thread 锁。
        max_byte: 活动记录文件与索引的 UTF-8 序列化总量 soft cap。
    """

    def __init__(self, workspace: Workspace, *, max_byte: int = DEFAULT_MEMORY_MAX_BYTE) -> None:
        if max_byte <= 0:
            raise ValueError("记忆总量上限必须大于 0")
        self._workspace = workspace
        self._max_byte = max_byte

    def list(self, thread_id: str) -> builtins.list[MemoryRecord]:
        """按 slug 列出当前活动记录，不会创建 memdir。

        Args:
            thread_id: 会话标识。

        Returns:
            记录列表；已有 workspace 尚无 memdir 时为空列表。
        """
        with self._workspace.thread_lock(thread_id):
            memory = self._memory_dir(thread_id, create=False)
            if memory is None:
                return []
            return self._scan(memory)

    def export(self, thread_id: str) -> MemoryStoreSnapshot:
        """在同一把 thread 锁内导出全量正文与 CAS 版本，不创建目录。"""
        with self._workspace.thread_lock(thread_id):
            memory = self._memory_dir(thread_id, create=False)
            records = () if memory is None else tuple(self._scan(memory))
            return MemoryStoreSnapshot(records=records, version=_version(records))

    def read(self, thread_id: str, slug: str) -> MemoryRecord:
        """读取一条记忆，不会创建 memdir。

        Args:
            thread_id: 会话标识。
            slug: 记录文件的 slug。

        Returns:
            解析与校验后的记忆。

        Raises:
            FileNotFoundError: workspace、memdir 或记录不存在。
            MemoryStoreError: slug、符号链接或文件 schema 不合法。
        """
        _validate_slug(slug)
        with self._workspace.thread_lock(thread_id):
            memory = self._memory_dir(thread_id, create=False)
            if memory is None:
                raise FileNotFoundError(f"记忆目录不存在：{thread_id!r}")
            return self._read_record(memory / f"{slug}.md", slug)

    def write(self, thread_id: str, record: MemoryRecord) -> MemoryRecord:
        """原子写入一条记忆并在同一 thread 锁内重建索引。

        Args:
            thread_id: 会话标识。
            record: 已通过上层准入的记忆。

        Returns:
            写入的记录。

        Raises:
            FileNotFoundError: workspace 不存在。
            MemoryStoreError: 记录 schema 或物理路径不合法。
            OSError: 磁盘写入失败，包括同 workspace 配额写满。
        """
        with self._workspace.thread_lock(thread_id):
            workspace = self._workspace.lookup(thread_id)
            memory = self._memory_dir(thread_id, create=False)
            current = [] if memory is None else self._scan(memory)
            records = {one.slug: one for one in current}
            records[record.slug] = record
            snapshot = self._replace_locked(workspace, memory, tuple(records.values()), expected_version=None)
            return next(one for one in snapshot.records if one.slug == record.slug)

    def delete(self, thread_id: str, slug: str) -> None:
        """物理删除一条记忆并立即重建索引。

        Args:
            thread_id: 会话标识。
            slug: 记录 slug。

        Raises:
            FileNotFoundError: workspace、memdir 或记录不存在。
            MemoryStoreError: slug 或符号链接不合法。
        """
        _validate_slug(slug)
        with self._workspace.thread_lock(thread_id):
            memory = self._memory_dir(thread_id, create=False)
            if memory is None:
                raise FileNotFoundError(f"记忆目录不存在：{thread_id!r}")
            current = self._scan(memory)
            if not any(one.slug == slug for one in current):
                raise FileNotFoundError(f"记忆不存在：{slug!r}")
            workspace = self._workspace.lookup(thread_id)
            self._replace_locked(
                workspace,
                memory,
                tuple(one for one in current if one.slug != slug),
                expected_version=None,
            )

    def replace(
        self,
        thread_id: str,
        records: tuple[MemoryRecord, ...],
        *,
        expected_version: str | None = None,
    ) -> MemoryStoreSnapshot:
        """全量替换活动集；校验、容量检查、提交与异常恢复均在同一 thread 锁内。"""
        with self._workspace.thread_lock(thread_id):
            workspace = self._workspace.lookup(thread_id)
            memory = self._memory_dir(thread_id, create=False)
            return self._replace_locked(workspace, memory, records, expected_version=expected_version)

    def rebuild_index(self, thread_id: str) -> Path | None:
        """从活动 Markdown 文件重建短索引，不会创建 memdir。

        Args:
            thread_id: 会话标识。

        Returns:
            索引路径；已有 workspace 尚无 memdir 时为空。
        """
        with self._workspace.thread_lock(thread_id):
            memory = self._memory_dir(thread_id, create=False)
            return None if memory is None else self._rebuild_index(memory)

    def _memory_dir(self, thread_id: str, *, create: bool) -> Path | None:
        workspace = self._workspace.lookup(thread_id)
        memory = workspace / MEMORY_DIR
        if memory.is_symlink():
            raise MemoryStoreError("记忆目录不能是符号链接")
        if memory.exists():
            if not memory.is_dir():
                raise MemoryStoreError("记忆路径不是目录")
            if any((memory / name).exists() or (memory / name).is_symlink() for name in _MEMORY_TRANSACTION_ENTRY):
                _recover_transaction_artifacts(memory)
            return memory
        if not create:
            return None
        memory.mkdir(mode=0o700)
        _sync_directory(workspace)
        return memory

    def _scan(self, memory: Path) -> builtins.list[MemoryRecord]:
        found: builtins.list[MemoryRecord] = []
        for target in sorted(memory.glob("*.md")):
            if target.name == MEMORY_INDEX:
                continue
            _validate_slug(target.stem)
            found.append(self._read_record(target, target.stem))
        return found

    def _read_record(self, target: Path, slug: str) -> MemoryRecord:
        _reject_symlink(target)
        raw = target.read_text(encoding="utf-8")
        if not raw.startswith("---\n") or "\n---\n" not in raw[4:]:
            raise MemoryStoreError(f"记忆 frontmatter 不完整：{target.name}")
        frontmatter, content = raw[4:].split("\n---\n", 1)
        try:
            loaded: object = yaml.safe_load(frontmatter)
        except yaml.YAMLError as error:
            raise MemoryStoreError(f"记忆 frontmatter 无法解析：{target.name}") from error
        if not isinstance(loaded, dict) or set(loaded) != _FRONTMATTER_KEY:
            raise MemoryStoreError(f"记忆 frontmatter 必须且只能包含 name、description、type：{target.name}")
        if not all(isinstance(loaded[key], str) for key in _FRONTMATTER_KEY):
            raise MemoryStoreError(f"记忆 frontmatter 字段必须是字符串：{target.name}")
        record = MemoryRecord(
            slug=slug,
            name=loaded["name"],
            description=loaded["description"],
            type=loaded["type"],
            content=content.removeprefix("\n").removesuffix("\n"),
            updated_at=datetime.fromtimestamp(target.stat().st_mtime, tz=UTC),
        )
        _validate_record(record)
        return record

    def _rebuild_index(self, memory: Path) -> Path:
        records = self._scan(memory)
        index = memory / MEMORY_INDEX
        _reject_symlink(index)
        _, content = self._prepare(tuple(records))
        _atomic_write(index, content)
        return index

    def _replace_locked(
        self,
        workspace: Path,
        memory: Path | None,
        records: tuple[MemoryRecord, ...],
        *,
        expected_version: str | None,
    ) -> MemoryStoreSnapshot:
        target = workspace / MEMORY_DIR
        if target.exists():
            _recover_transaction_artifacts(target)
        memory = target if target.exists() else None
        current = () if memory is None else tuple(self._scan(memory))
        current_version = _version(current)
        if expected_version is not None and expected_version != current_version:
            raise MemoryVersionConflictError("记忆版本已变化，请基于最新版本重试")

        payloads, index = self._prepare(records)
        _replace_files(target, payloads, index)
        stored = tuple(self._scan(target))
        return MemoryStoreSnapshot(records=stored, version=_version(stored))

    def _prepare(self, records: tuple[MemoryRecord, ...]) -> tuple[builtins.list[tuple[MemoryRecord, bytes]], bytes]:
        ordered = sorted(records, key=lambda one: one.slug)
        if len({one.slug for one in ordered}) != len(ordered):
            raise MemoryStoreError("全量记忆中存在重复 slug")

        payloads: builtins.list[tuple[MemoryRecord, bytes]] = []
        for record in ordered:
            _validate_record(record)
            payloads.append((record, _serialize(record).encode()))
        index = _serialize_index(ordered)
        if len(index) > MAX_MEMORY_INDEX_BYTE:
            raise MemoryCapacityError(f"记忆索引超过 {MAX_MEMORY_INDEX_BYTE} 字节上限")
        total = len(index) + sum(len(content) for _, content in payloads)
        if total > self._max_byte:
            raise MemoryCapacityError(f"记忆序列化总量超过 {self._max_byte} 字节上限")
        return payloads, index


def _validate_slug(slug: str) -> None:
    if slug == MEMORY_INDEX.removesuffix(".md") or _SLUG.fullmatch(slug) is None:
        raise MemoryStoreError(f"记忆 slug 不合法：{slug!r}")


def _validate_record(record: MemoryRecord) -> None:
    _validate_slug(record.slug)
    for name, value in (("name", record.name), ("description", record.description), ("content", record.content)):
        if not value.strip():
            raise MemoryStoreError(f"记忆 {name} 不能为空")
    if "\n" in record.name or "\n" in record.description:
        raise MemoryStoreError("记忆 name 与 description 不能换行")
    if record.type not in MEMORY_TYPE:
        raise MemoryStoreError(f"记忆 type 不合法：{record.type!r}")
    if len(record.content) > MAX_MEMORY_CONTENT_CHARACTER:
        raise MemoryCapacityError(f"单条记忆正文超过 {MAX_MEMORY_CONTENT_CHARACTER} 字符上限")


def _serialize(record: MemoryRecord) -> str:
    frontmatter = yaml.safe_dump(
        {"name": record.name, "description": record.description, "type": record.type},
        allow_unicode=True,
        sort_keys=False,
    )
    return f"---\n{frontmatter}---\n\n{record.content.rstrip()}\n"


def _serialize_index(records: list[MemoryRecord]) -> bytes:
    line = ["# 记忆索引", ""]
    line.extend(f"- [{one.name}]({one.slug}.md): {one.description} (`{one.type}`)" for one in records)
    return ("\n".join(line).rstrip() + "\n").encode()


def _version(records: tuple[MemoryRecord, ...]) -> str:
    digest = hashlib.sha256()
    for record in sorted(records, key=lambda one: one.slug):
        name = f"{record.slug}.md".encode()
        content = _serialize(record).encode()
        digest.update(len(name).to_bytes(4, "big"))
        digest.update(name)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def _replace_files(
    memory: Path,
    payloads: list[tuple[MemoryRecord, bytes]],
    index: bytes,
) -> None:
    """在固定 memdir 内预构建并锁内提交；任何提交异常都恢复原文件集。"""
    created_memory = not memory.exists()
    if created_memory:
        memory.mkdir(mode=0o700)
        _sync_directory(memory.parent)
    stage = memory / MEMORY_STAGE_DIR
    backup = memory / MEMORY_BACKUP_DIR
    promoting = memory / MEMORY_PROMOTING_MARKER
    committed = memory / MEMORY_COMMITTED_MARKER
    if any(path.exists() or path.is_symlink() for path in (stage, backup, promoting, committed)):
        raise MemoryStoreError("记忆事务临时项未清理")
    moved: builtins.list[str] = []
    promoted: builtins.list[str] = []
    try:
        stage.mkdir(mode=0o700)
        backup.mkdir(mode=0o700)
        for record, content in payloads:
            _write_stage_file(stage / f"{record.slug}.md", content, updated_at=record.updated_at)
        _write_stage_file(stage / MEMORY_INDEX, index, updated_at=None)
        _sync_directory(stage)
        _sync_directory(memory)

        for target in _active_entries(memory):
            os.replace(target, backup / target.name)
            moved.append(target.name)
        _write_stage_file(promoting, b"", updated_at=None)
        _sync_directory(backup)
        _sync_directory(memory)

        for target in sorted(stage.iterdir(), key=lambda one: one.name):
            os.replace(target, memory / target.name)
            promoted.append(target.name)
        os.replace(promoting, committed)
        _sync_directory(memory)
    except Exception:
        if committed.exists():
            logger.warning("记忆新版本已提交，持久化或清理将在下次访问继续：%s", memory, exc_info=True)
        else:
            try:
                for name in promoted:
                    _remove_path(memory / name)
                for name in moved:
                    source = backup / name
                    if source.exists() or source.is_symlink():
                        os.replace(source, memory / name)
                _remove_path(stage)
                _remove_path(backup)
                promoting.unlink(missing_ok=True)
                if created_memory and not any(memory.iterdir()):
                    memory.rmdir()
                    _sync_directory(memory.parent)
                else:
                    _sync_directory(memory)
            except Exception as rollback_error:
                raise MemoryStoreError("记忆文件集提交失败且无法恢复原快照") from rollback_error
            raise

    try:
        _remove_path(backup)
        _remove_path(stage)
        committed.unlink()
        _sync_directory(memory)
    except Exception:
        # committed marker 必须最后删除；留下它后，下次访问会保留新集并继续清理。
        logger.warning("记忆新版本已提交，旧备份清理失败并留待下次访问：%s", memory, exc_info=True)


def _recover_transaction_artifacts(memory: Path) -> None:
    """按 phase marker 恢复崩溃遗留事务，不把半状态暴露给下一次读取。"""
    if memory.is_symlink():
        raise MemoryStoreError("记忆目录不能是符号链接")
    stage = memory / MEMORY_STAGE_DIR
    backup = memory / MEMORY_BACKUP_DIR
    promoting = memory / MEMORY_PROMOTING_MARKER
    committed = memory / MEMORY_COMMITTED_MARKER
    for artifact in (stage, backup, promoting, committed):
        if artifact.is_symlink():
            raise MemoryStoreError(f"记忆事务项不能是符号链接：{artifact.name}")
    if stage.exists() and not stage.is_dir():
        raise MemoryStoreError("记忆 staging 路径不是目录")
    if backup.exists() and not backup.is_dir():
        raise MemoryStoreError("记忆备份路径不是目录")

    if committed.exists():
        _remove_path(backup)
        _remove_path(stage)
        promoting.unlink(missing_ok=True)
        committed.unlink()
        _sync_directory(memory)
        return

    if backup.exists():
        if promoting.exists():
            for target in _active_entries(memory):
                _remove_path(target)
        for target in sorted(backup.iterdir(), key=lambda one: one.name):
            os.replace(target, memory / target.name)
        _remove_path(backup)
    _remove_path(stage)
    promoting.unlink(missing_ok=True)
    _sync_directory(memory)


def _active_entries(memory: Path) -> builtins.list[Path]:
    return sorted(
        (target for target in memory.iterdir() if target.name not in _MEMORY_TRANSACTION_ENTRY),
        key=lambda one: one.name,
    )


def _remove_path(target: Path) -> None:
    if target.is_symlink() or target.is_file():
        target.unlink(missing_ok=True)
    elif target.is_dir():
        shutil.rmtree(target)


def _write_stage_file(target: Path, content: bytes, *, updated_at: datetime | None) -> None:
    with target.open("xb") as opened:
        os.fchmod(opened.fileno(), 0o600)
        opened.write(content)
        opened.flush()
        if updated_at is not None:
            timestamp = updated_at.timestamp()
            os.utime(target, (timestamp, timestamp))
        os.fsync(opened.fileno())


def _reject_symlink(target: Path) -> None:
    if target.is_symlink():
        raise MemoryStoreError(f"记忆文件不能是符号链接：{target.name}")


def _atomic_write(target: Path, content: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as opened:
            opened.write(content)
            opened.flush()
            os.fsync(opened.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
        _sync_directory(target.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _sync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
