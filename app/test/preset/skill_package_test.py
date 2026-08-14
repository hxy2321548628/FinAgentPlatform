"""Skill 上传包校验器的测试；恶意场景全部由真实 ZIP 字节现造。"""

from io import BytesIO
from pathlib import PurePosixPath
from stat import S_IFLNK
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pytest

from preset.skill_package import (
    ALLOWED_EXTENSION,
    MAX_FILE_COUNT,
    MAX_FILE_SIZE,
    MAX_TOTAL_SIZE,
    validate_skill_package,
)


def _skill_markdown(*, name: str = "annualized-naming", description: str = "年化口径") -> bytes:
    return f"---\nname: {name}\ndescription: {description}\n---\n按 252 个交易日年化。\n".encode()


def _zip(files: dict[str, bytes], *, symlink: tuple[str, str] | None = None) -> bytes:
    target = BytesIO()
    with ZipFile(target, "w", compression=ZIP_DEFLATED) as archive:
        for path, content in files.items():
            archive.writestr(path, content)
        if symlink is not None:
            path, destination = symlink
            info = ZipInfo(path)
            info.create_system = 3
            info.external_attr = (S_IFLNK | 0o777) << 16
            archive.writestr(info, destination)
    return target.getvalue()


def _valid_zip(**extra: bytes) -> bytes:
    files = {"annualized-naming/SKILL.md": _skill_markdown()}
    files.update(extra)
    return _zip(files)


def _reasons(content: bytes, filename: str = "skill.zip") -> tuple[str, ...]:
    result = validate_skill_package(content, filename=filename)
    assert result.package is None
    return result.reasons


def test_a_valid_zip_returns_normalized_files_and_frontmatter() -> None:
    result = validate_skill_package(
        _valid_zip(**{"annualized-naming/notes/口径.txt": "说明".encode()}),
        filename="annualized.zip",
    )

    assert result.reasons == ()
    assert result.package is not None
    assert result.package.name == "annualized-naming"
    assert result.package.description == "年化口径"
    assert result.package.file_count == 2
    assert result.package.total_bytes == sum(len(one.content) for one in result.package.files)
    assert {one.path for one in result.package.files} == {"SKILL.md", "notes/口径.txt"}


def test_a_single_markdown_is_wrapped_as_skill_md() -> None:
    result = validate_skill_package(_skill_markdown(), filename="annualized-naming.md")

    assert result.reasons == ()
    assert result.package is not None
    assert [(one.path, one.content) for one in result.package.files] == [("SKILL.md", _skill_markdown())]


def test_path_traversal_is_rejected() -> None:
    reasons = _reasons(
        _zip(
            {
                "annualized-naming/SKILL.md": _skill_markdown(),
                "annualized-naming/../../etc/passwd": b"x",
            }
        )
    )

    assert any("路径" in one for one in reasons)


def test_symbolic_link_is_rejected() -> None:
    reasons = _reasons(
        _zip(
            {"annualized-naming/SKILL.md": _skill_markdown()},
            symlink=("annualized-naming/passwd.txt", "/etc/passwd"),
        )
    )

    assert any("符号链接" in one for one in reasons)


def test_declared_total_size_over_limit_is_rejected_with_actual_size() -> None:
    content = b"x" * (MAX_TOTAL_SIZE + 1)
    reasons = _reasons(_valid_zip(**{"annualized-naming/large.txt": content}))

    assert any("总大小" in one and str(len(content) + len(_skill_markdown())) in one for one in reasons)


def test_file_count_over_limit_is_rejected() -> None:
    extras = {f"annualized-naming/note-{index}.txt": b"x" for index in range(MAX_FILE_COUNT)}
    reasons = _reasons(_valid_zip(**extras))

    assert any("文件数量" in one and str(MAX_FILE_COUNT + 1) in one for one in reasons)


def test_high_compression_ratio_is_rejected_before_reading_members() -> None:
    package = _valid_zip(**{"annualized-naming/bomb.txt": b"0" * 200_000})

    with patch.object(ZipFile, "read", side_effect=AssertionError("不应读取成员")):
        reasons = _reasons(package)

    assert any("压缩比" in one for one in reasons)


def test_disallowed_extension_is_rejected_with_the_file_name() -> None:
    reasons = _reasons(_valid_zip(**{"annualized-naming/scripts/run.sh": b"exit 0"}))

    assert any("扩展名" in one and "scripts/run.sh" in one for one in reasons)
    assert ".sh" not in ALLOWED_EXTENSION


def test_one_file_over_limit_is_rejected_with_the_file_name() -> None:
    reasons = _reasons(_valid_zip(**{"annualized-naming/oversized.txt": b"x" * (MAX_FILE_SIZE + 1)}))

    assert any("单文件" in one and "oversized.txt" in one for one in reasons)


@pytest.mark.parametrize(
    ("directory", "name"),
    [("annualized-naming", "财务指标"), ("another-name", "annualized-naming")],
)
def test_invalid_or_mismatched_frontmatter_name_is_rejected(directory: str, name: str) -> None:
    package = _zip({f"{directory}/SKILL.md": _skill_markdown(name=name)})

    reasons = _reasons(package)

    assert any("name" in one for one in reasons)


def test_zip_must_have_one_root_directory_with_skill_md() -> None:
    package = _zip(
        {
            "first/SKILL.md": _skill_markdown(name="first"),
            "second/note.txt": b"x",
        }
    )

    reasons = _reasons(package)

    assert any("根目录" in one for one in reasons)


def test_all_returned_paths_are_relative_posix_paths() -> None:
    result = validate_skill_package(_valid_zip(), filename="skill.zip")

    assert result.package is not None
    assert all(not PurePosixPath(one.path).is_absolute() for one in result.package.files)
