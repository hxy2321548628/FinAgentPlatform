from pathlib import Path

import pytest

from app.sandbox.browse import preview, tree


def paths(root: Path) -> list[str]:
    return [one.path for one in tree(root).entries]


# ------------------------------------------------------------------ 目录树
def test_a_file_at_the_root_shows_up(tmp_path: Path) -> None:
    (tmp_path / "holdings.csv").write_bytes(b"a,b\n")

    assert paths(tmp_path) == ["holdings.csv"]


def test_a_nested_file_carries_its_relative_path(tmp_path: Path) -> None:
    (tmp_path / "outputs").mkdir()
    (tmp_path / "outputs" / "chart.png").write_bytes(b"png")

    assert paths(tmp_path) == ["outputs", "outputs/chart.png"]


def test_an_empty_directory_still_shows_up(tmp_path: Path) -> None:
    """侧边栏要显示空的 outputs/，因此不能只列文件。"""
    (tmp_path / "outputs").mkdir()

    assert paths(tmp_path) == ["outputs"]


def test_a_directory_is_marked_as_one(tmp_path: Path) -> None:
    (tmp_path / "outputs").mkdir()

    assert tree(tmp_path).entries[0].is_dir


def test_a_file_reports_its_size(tmp_path: Path) -> None:
    (tmp_path / "holdings.csv").write_bytes(b"a,b\n")

    assert tree(tmp_path).entries[0].size == 4


def test_a_parent_sorts_before_its_children(tmp_path: Path) -> None:
    """前端按顺序拼树，父目录必须先到。"""
    (tmp_path / "outputs" / "figure").mkdir(parents=True)
    (tmp_path / "outputs" / "figure" / "chart.png").write_bytes(b"png")

    assert paths(tmp_path) == ["outputs", "outputs/figure", "outputs/figure/chart.png"]


def test_a_symlink_is_left_out(tmp_path: Path) -> None:
    """Agent 在沙箱里建得出符号链接，列进树里就等于把宿主文件摆上货架。"""
    secret = tmp_path.parent / "secret.txt"
    secret.write_text("凭据", encoding="utf-8")
    root = tmp_path / "space"
    root.mkdir()
    (root / "link.txt").symlink_to(secret)

    assert paths(root) == []


def test_a_symlinked_directory_is_not_walked_into(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("凭据", encoding="utf-8")
    root = tmp_path / "space"
    root.mkdir()
    (root / "door").symlink_to(outside, target_is_directory=True)

    assert paths(root) == []


def test_too_many_entries_are_cut_off(tmp_path: Path) -> None:
    """Agent 可以在配额之内造出上万个小文件，整棵树发出去会把浏览器打死。"""
    for index in range(5):
        (tmp_path / f"{index}.txt").write_bytes(b"x")

    found = tree(tmp_path, limit=3)

    assert len(found.entries) == 3
    assert found.truncated


def test_a_tree_within_the_limit_is_not_truncated(tmp_path: Path) -> None:
    (tmp_path / "holdings.csv").write_bytes(b"x")

    assert not tree(tmp_path, limit=3).truncated


def test_an_empty_workspace_gives_an_empty_tree(tmp_path: Path) -> None:
    assert paths(tmp_path) == []


# ------------------------------------------------------------------ 预览
def test_a_text_file_comes_back_as_text(tmp_path: Path) -> None:
    target = tmp_path / "analyze.py"
    target.write_text("import pandas\nprint(1)\n", encoding="utf-8")

    assert preview(target).text == "import pandas\nprint(1)"


def test_the_line_count_is_reported(tmp_path: Path) -> None:
    target = tmp_path / "analyze.py"
    target.write_text("一\n二\n三\n", encoding="utf-8")

    assert preview(target).total_line == 3


def test_a_window_starts_where_asked(tmp_path: Path) -> None:
    target = tmp_path / "analyze.py"
    target.write_text("一\n二\n三\n四\n", encoding="utf-8")

    found = preview(target, offset=1, limit=2)

    assert found.text == "二\n三"
    assert (found.start_line, found.end_line) == (2, 3)


def test_a_window_past_the_end_is_empty(tmp_path: Path) -> None:
    target = tmp_path / "analyze.py"
    target.write_text("一\n", encoding="utf-8")

    found = preview(target, offset=9)

    assert found.text == ""
    assert found.total_line == 1


def test_an_empty_file_previews_as_empty(tmp_path: Path) -> None:
    """框架的 read 会在这里塞一句给 LLM 看的提醒，教师不该看到那句话。"""
    target = tmp_path / "empty.txt"
    target.write_bytes(b"")

    found = preview(target)

    assert found.text == ""
    assert found.total_line == 0
    assert not found.is_binary


def test_a_binary_file_is_flagged_instead_of_decoded(tmp_path: Path) -> None:
    target = tmp_path / "chart.png"
    target.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00")

    found = preview(target)

    assert found.is_binary
    assert found.text == ""


def test_a_binary_file_without_a_telltale_extension_is_still_flagged(tmp_path: Path) -> None:
    """框架的 read 按扩展名判类型，这一条正是它会解码失败的地方。"""
    target = tmp_path / "model.pkl"
    target.write_bytes(b"\x80\x04\x95\xff\xfe\xfd")

    assert preview(target).is_binary


def test_a_long_file_is_read_only_at_the_head(tmp_path: Path) -> None:
    target = tmp_path / "big.csv"
    target.write_text("a\nb\nc\nd\n", encoding="utf-8")

    found = preview(target, max_byte=4)

    assert found.truncated
    assert found.text == "a\nb"


def test_a_short_file_is_not_marked_truncated(tmp_path: Path) -> None:
    target = tmp_path / "small.csv"
    target.write_bytes(b"a,b\n")

    assert not preview(target, max_byte=64).truncated


def test_cutting_a_multibyte_character_in_half_does_not_read_as_binary(tmp_path: Path) -> None:
    """截断读会切在字符中间，按「解不出来就是二进制」直接判会把中文文件全判错。"""
    target = tmp_path / "notes.txt"
    target.write_text("中文内容", encoding="utf-8")

    found = preview(target, max_byte=4)

    assert not found.is_binary
    assert found.text == "中"


@pytest.mark.parametrize("offset", [-1, -100])
def test_a_negative_offset_clamps_to_the_start(tmp_path: Path, offset: int) -> None:
    target = tmp_path / "analyze.py"
    target.write_text("一\n二\n", encoding="utf-8")

    assert preview(target, offset=offset).start_line == 1
