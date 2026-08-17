"""Broker 持有的 Skill 字节仓库与 workspace 物化。"""

import logging
import os
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
from shutil import rmtree

from app.sandbox.path import SKILL_DIR

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SkillFile:
    """一个相对于 Skill 根目录的文件。"""

    path: str
    content: bytes


@dataclass(frozen=True)
class SkillVersionFile:
    """Skill 发布版本里一个可浏览文件的元数据。"""

    path: str
    size: int


@dataclass(frozen=True)
class SkillReference:
    """一次 run 快照里冻结的 Skill 版本。"""

    skill_id: str
    version: int
    name: str


class SkillStore:
    """宿主机 Skill 版本仓库，以及到 workspace 的全量对齐。"""

    def __init__(self, root: Path) -> None:
        self._root = root

    def save_version(self, skill_id: str, version: int, files: tuple[SkillFile, ...]) -> None:
        """把一版已经校验过的文件清单落到宿主机仓库。"""
        target = self._version_path(skill_id, version)
        normalized = _normalized_files(files)
        if target.exists() or target.is_symlink():
            _remove(target)
        target.mkdir(parents=True)
        for relative, content in normalized:
            destination = target.joinpath(*relative.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)

    def list_version(self, skill_id: str, version: int) -> tuple[SkillVersionFile, ...]:
        """列出一版 Skill 中的全部普通文件，不跟随符号链接。"""
        root = self._existing_version(skill_id, version)
        return tuple(
            SkillVersionFile(path=source.relative_to(root).as_posix(), size=source.stat().st_size)
            for source in sorted(root.rglob("*"))
            if source.is_file() and not source.is_symlink()
        )

    def read_version_file(self, skill_id: str, version: int, path: str) -> bytes:
        """读取一版 Skill 中的普通文件；路径只能位于该版本目录内。"""
        root = self._existing_version(skill_id, version)
        relative = _relative_file(path)
        target = root.joinpath(*relative.parts)
        if target.is_symlink() or not target.is_file():
            raise FileNotFoundError(f"Skill 文件不存在：{path}")
        return target.read_bytes()

    def _existing_version(self, skill_id: str, version: int) -> Path:
        root = self._version_path(skill_id, version)
        if not root.is_dir():
            raise FileNotFoundError(f"Skill 版本不存在：{skill_id}/{version}")
        return root

    def align(self, workspace: Path, references: tuple[SkillReference, ...]) -> None:
        """把快照指定的版本全量对齐到 ``workspace/skill``。

        缺失文件补齐、内容 hash 不同则覆盖、清单外文件和目录全部删除。仓库版本
        缺失时先失败，不改 workspace，避免得到一半新一半旧的 Skill 集合。
        """
        desired = self._desired_files(references)
        desired_files = set(desired)
        desired_directories = _parent_directories(desired_files)
        target_root = workspace / SKILL_DIR
        owner = workspace.stat().st_uid, workspace.stat().st_gid

        if target_root.is_symlink() or (target_root.exists() and not target_root.is_dir()):
            logger.warning("覆盖 workspace 中类型不符的 Skill 根目录：%s", target_root)
            _remove(target_root)
        target_root.mkdir(parents=True, exist_ok=True)
        _set_owner(target_root, owner)

        for relative, target in _existing_entries(target_root):
            expected_file = relative in desired_files
            expected_directory = relative in desired_directories
            if (
                target.is_symlink()
                or (expected_file and not target.is_file())
                or (expected_directory and not target.is_dir())
            ):
                logger.warning("覆盖 workspace 中类型不符的 Skill 路径：%s", target)
                _remove(target)
            elif not expected_file and not expected_directory:
                logger.warning("删除 workspace 中清单外的 Skill 路径：%s", target)
                _remove(target)

        for relative in sorted(desired_directories, key=lambda one: (len(one.parts), one.as_posix())):
            directory = target_root.joinpath(*relative.parts)
            directory.mkdir(parents=True, exist_ok=True)
            _set_owner(directory, owner)

        for relative, source in sorted(desired.items(), key=lambda one: one[0].as_posix()):
            destination = target_root.joinpath(*relative.parts)
            if destination.is_file() and _digest(destination) == _digest(source):
                continue
            if destination.exists() or destination.is_symlink():
                logger.warning("覆盖 workspace 中内容不同的 Skill 文件：%s", destination)
                _remove(destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(source.read_bytes())
            _set_owner(destination, owner)

    def _desired_files(self, references: tuple[SkillReference, ...]) -> dict[PurePosixPath, Path]:
        desired: dict[PurePosixPath, Path] = {}
        names: set[str] = set()
        for reference in references:
            name = _component(reference.name, label="Skill 名称")
            if name in names:
                raise ValueError(f"Skill 名称重复：{name}")
            names.add(name)
            source_root = self._version_path(reference.skill_id, reference.version)
            if not source_root.is_dir():
                raise FileNotFoundError(f"Skill 版本不存在：{reference.skill_id}/{reference.version}")
            for source in sorted(source_root.rglob("*")):
                if source.is_symlink() or not source.is_file():
                    continue
                relative = PurePosixPath(name) / PurePosixPath(source.relative_to(source_root).as_posix())
                desired[relative] = source
        return desired

    def _version_path(self, skill_id: str, version: int) -> Path:
        identifier = _component(skill_id, label="Skill 标识")
        if version < 1:
            raise ValueError(f"Skill 版本必须大于 0：{version}")
        return self._root / identifier / str(version)


def _relative_file(path: str) -> PurePosixPath:
    relative = PurePosixPath(path)
    if relative.is_absolute() or not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise ValueError(f"Skill 文件路径不合法：{path!r}")
    if "\\" in path:
        raise ValueError(f"Skill 文件路径不合法：{path!r}")
    return relative


def _normalized_files(files: tuple[SkillFile, ...]) -> tuple[tuple[PurePosixPath, bytes], ...]:
    normalized: list[tuple[PurePosixPath, bytes]] = []
    seen: set[PurePosixPath] = set()
    for file in files:
        path = PurePosixPath(file.path)
        if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
            raise ValueError(f"Skill 文件路径不合法：{file.path!r}")
        if "\\" in file.path:
            raise ValueError(f"Skill 文件路径不合法：{file.path!r}")
        if path in seen:
            raise ValueError(f"Skill 文件路径重复：{file.path!r}")
        seen.add(path)
        normalized.append((path, file.content))
    return tuple(normalized)


def _component(value: str, *, label: str) -> str:
    if not value or value in {".", ".."} or "/" in value or "\\" in value:
        raise ValueError(f"{label}不能作为目录名：{value!r}")
    return value


def _parent_directories(files: set[PurePosixPath]) -> set[PurePosixPath]:
    directories: set[PurePosixPath] = set()
    for file in files:
        directories.update(parent for parent in file.parents if parent != PurePosixPath("."))
    return directories


def _existing_entries(root: Path) -> list[tuple[PurePosixPath, Path]]:
    entries: list[tuple[PurePosixPath, Path]] = []
    for current, directories, files in os.walk(root, topdown=False, followlinks=False):
        base = Path(current)
        for name in files:
            target = base / name
            entries.append((PurePosixPath(target.relative_to(root).as_posix()), target))
        for name in directories:
            target = base / name
            entries.append((PurePosixPath(target.relative_to(root).as_posix()), target))
    return entries


def _digest(path: Path) -> bytes:
    return sha256(path.read_bytes()).digest()


def _remove(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        rmtree(path)


def _set_owner(path: Path, owner: tuple[int, int]) -> None:
    os.chown(path, *owner)
