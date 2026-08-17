"""Skill 上传包的纯字节校验。

本模块只接受内存中的上传字节并返回规范化文件清单，不碰磁盘、不查数据库、不认识
HTTP。所有 ZIP 结构与声明大小检查都先于成员读取，避免把 zip 炸弹解压后才发现超限。
"""

import re
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePosixPath
from zipfile import BadZipFile, LargeZipFile, ZipFile, ZipInfo, is_zipfile

import yaml

MAX_TOTAL_SIZE = 5 * 1024 * 1024
MAX_FILE_COUNT = 100
MAX_COMPRESSION_RATIO = 100
MAX_FILE_SIZE = 1 * 1024 * 1024
MAX_SKILL_NAME_LENGTH = 64
MAX_SKILL_DESCRIPTION_LENGTH = 1024
ALLOWED_EXTENSION = frozenset({".md", ".txt", ".py", ".csv", ".json", ".yaml", ".toml", ".html"})

SKILL_FILE_NAME = "SKILL.md"
FRONTMATTER_DELIMITER = "---"
SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True)
class SkillFile:
    """一个经过校验、相对于 skill 根目录的文件。"""

    path: str
    content: bytes


@dataclass(frozen=True)
class ValidatedSkillPackage:
    """校验通过后供存储层直接使用的 skill 包。"""

    name: str
    description: str
    files: tuple[SkillFile, ...]
    file_count: int
    total_bytes: int


@dataclass(frozen=True)
class SkillPackageValidation:
    """校验结果；`package` 与 `reasons` 必有且仅有一方有值。"""

    package: ValidatedSkillPackage | None
    reasons: tuple[str, ...]


def validate_skill_package(content: bytes, *, filename: str) -> SkillPackageValidation:
    """校验 ZIP 或单个 Markdown，并返回统一的目录内文件清单。

    Args:
        content: 上传的原始字节。
        filename: 上传文件名，只用来区分 ZIP 与单 Markdown。

    Returns:
        校验结果。失败时 `package` 为空且 `reasons` 含逐条中文原因。
    """
    suffix = PurePosixPath(filename).suffix.lower()
    if suffix == ".md":
        return _validate_markdown(content)
    if suffix != ".zip" or not is_zipfile(BytesIO(content)):
        return _rejected("只接受 ZIP 或单个 .md 文件")
    return _validate_zip(content)


def _validate_markdown(content: bytes) -> SkillPackageValidation:
    reasons = _size_reasons(((SKILL_FILE_NAME, len(content), len(content)),))
    if reasons:
        return _rejected(*reasons)
    metadata, metadata_reasons = _frontmatter(content, directory_name=None)
    if metadata is None:
        return _rejected(*metadata_reasons)
    name, description = metadata
    return _accepted(name, description, (SkillFile(path=SKILL_FILE_NAME, content=content),))


def _validate_zip(content: bytes) -> SkillPackageValidation:
    try:
        with ZipFile(BytesIO(content)) as archive:
            members = [one for one in archive.infolist() if not one.is_dir()]
            reasons = _zip_header_reasons(members)
            root, root_reasons = _skill_root(members)
            reasons.extend(root_reasons)
            if reasons or root is None:
                return _rejected(*reasons)
            files = _read_members(archive, members, root)
    except (BadZipFile, LargeZipFile, RuntimeError, ValueError) as error:
        return _rejected(f"ZIP 无法读取：{error}")

    skill_file = next((one for one in files if one.path == SKILL_FILE_NAME), None)
    if skill_file is None:
        return _rejected("根目录必须包含唯一的 SKILL.md")
    metadata, reasons = _frontmatter(skill_file.content, directory_name=root)
    if metadata is None:
        return _rejected(*reasons)
    name, description = metadata
    return _accepted(name, description, files)


def _zip_header_reasons(members: list[ZipInfo]) -> list[str]:
    """只读 ZIP 目录头完成全部解压前闸门检查。"""
    reasons: list[str] = []
    described = tuple((one.filename, one.file_size, one.compress_size) for one in members)
    reasons.extend(_size_reasons(described))

    seen: set[str] = set()
    for member in members:
        path = member.filename
        if _unsafe_path(path):
            reasons.append(f"路径不合法：{path}")
        if path in seen:
            reasons.append(f"ZIP 内存在重复路径：{path}")
        seen.add(path)
        if stat.S_IFMT(member.external_attr >> 16) == stat.S_IFLNK:
            reasons.append(f"不允许符号链接：{path}")
        extension = PurePosixPath(path).suffix
        if extension not in ALLOWED_EXTENSION:
            reasons.append(f"文件扩展名不允许：{path}")
    return reasons


def _size_reasons(files: tuple[tuple[str, int, int], ...]) -> list[str]:
    reasons: list[str] = []
    file_count = len(files)
    total_size = sum(one[1] for one in files)
    compressed_size = sum(one[2] for one in files)
    if file_count > MAX_FILE_COUNT:
        reasons.append(f"文件数量为 {file_count}，超过上限 {MAX_FILE_COUNT}")
    if total_size > MAX_TOTAL_SIZE:
        reasons.append(f"解压后总大小为 {total_size} 字节，超过上限 {MAX_TOTAL_SIZE} 字节")
    for path, size, _ in files:
        if size > MAX_FILE_SIZE:
            reasons.append(f"单文件超过上限：{path} 为 {size} 字节，上限 {MAX_FILE_SIZE} 字节")
    if total_size > 0 and (compressed_size == 0 or total_size > compressed_size * MAX_COMPRESSION_RATIO):
        reasons.append(f"压缩比超过 {MAX_COMPRESSION_RATIO}:1：解压后 {total_size} 字节，压缩后 {compressed_size} 字节")
    return reasons


def _skill_root(members: list[ZipInfo]) -> tuple[str | None, list[str]]:
    if not members:
        return None, ["ZIP 不能为空"]
    paths = [PurePosixPath(one.filename) for one in members if not _unsafe_path(one.filename)]
    if len(paths) != len(members):
        return None, []
    if any(len(one.parts) < 2 for one in paths):
        return None, ["ZIP 必须只有一个根目录，文件不能直接放在 ZIP 顶层"]
    roots = {one.parts[0] for one in paths}
    if len(roots) != 1:
        return None, ["ZIP 必须只有一个根目录"]
    root = next(iter(roots))
    skill_files = [one for one in paths if one.parts == (root, SKILL_FILE_NAME)]
    if len(skill_files) != 1:
        return None, ["根目录必须包含唯一的 SKILL.md"]
    return root, []


def _read_members(archive: ZipFile, members: list[ZipInfo], root: str) -> tuple[SkillFile, ...]:
    prefix_length = len(root) + 1
    return tuple(
        SkillFile(path=one.filename[prefix_length:], content=archive.read(one))
        for one in sorted(members, key=lambda member: member.filename)
    )


def _frontmatter(content: bytes, *, directory_name: str | None) -> tuple[tuple[str, str] | None, list[str]]:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return None, ["SKILL.md 必须是 UTF-8 文本"]
    normalized = text.replace("\r\n", "\n")
    lines = normalized.splitlines()
    if not lines or lines[0] != FRONTMATTER_DELIMITER:
        return None, ["SKILL.md 必须以 YAML frontmatter 开头"]
    try:
        end = lines.index(FRONTMATTER_DELIMITER, 1)
    except ValueError:
        return None, ["SKILL.md 的 YAML frontmatter 没有结束分隔线"]
    try:
        loaded: object = yaml.safe_load("\n".join(lines[1:end]))
    except yaml.YAMLError as error:
        return None, [f"SKILL.md 的 YAML frontmatter 无法解析：{error}"]
    if not isinstance(loaded, Mapping):
        return None, ["SKILL.md 的 YAML frontmatter 必须是对象"]

    name = loaded.get("name")
    description = loaded.get("description")
    reasons = _metadata_reasons(name, description, directory_name=directory_name)
    if reasons or not isinstance(name, str) or not isinstance(description, str):
        return None, reasons
    return (name, description), []


def _metadata_reasons(name: object, description: object, *, directory_name: str | None) -> list[str]:
    reasons: list[str] = []
    if not isinstance(name, str) or not SKILL_NAME_PATTERN.fullmatch(name) or len(name) > MAX_SKILL_NAME_LENGTH:
        reasons.append("skill 的 name 必须是 1–64 位小写英文字母、数字与单个连字符")
    elif directory_name is not None and name != directory_name:
        reasons.append(f"skill 的 name 必须等于目录名：name={name}，目录={directory_name}")
    if not isinstance(description, str) or not description.strip():
        reasons.append("skill 的 description 不能为空")
    elif len(description) > MAX_SKILL_DESCRIPTION_LENGTH:
        reasons.append(f"skill 的 description 超过 {MAX_SKILL_DESCRIPTION_LENGTH} 字符")
    return reasons


def _unsafe_path(path: str) -> bool:
    candidate = PurePosixPath(path)
    return not path or "\\" in path or candidate.is_absolute() or ".." in candidate.parts or path.startswith("/")


def _accepted(name: str, description: str, files: tuple[SkillFile, ...]) -> SkillPackageValidation:
    return SkillPackageValidation(
        package=ValidatedSkillPackage(
            name=name,
            description=description,
            files=files,
            file_count=len(files),
            total_bytes=sum(len(one.content) for one in files),
        ),
        reasons=(),
    )


def _rejected(*reasons: str) -> SkillPackageValidation:
    return SkillPackageValidation(package=None, reasons=tuple(dict.fromkeys(reasons)))
