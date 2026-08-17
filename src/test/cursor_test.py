"""翻页游标的测试。"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from cursor import CursorError, decode, encode, split


def test_a_cursor_round_trips() -> None:
    when, identifier = datetime(2026, 8, 11, 10, 30, 45, 123456, tzinfo=UTC), uuid4()

    assert decode(encode(when, identifier)) == (when, identifier)


def test_microseconds_survive_the_round_trip() -> None:
    """精度丢一位就会让同一秒内提交的会话在翻页边界上互相顶掉。"""
    when = datetime(2026, 8, 11, 10, 30, 45, 1, tzinfo=UTC)
    identifier = uuid4()

    assert decode(encode(when, identifier))[0] == when


def test_a_cursor_does_not_leak_its_contents() -> None:
    """不透明是契约的一部分：调用方一旦开始解析它，游标的格式就再也改不动了。"""
    identifier = uuid4()

    assert identifier.hex not in encode(datetime.now(UTC), identifier)


def test_a_garbage_cursor_is_rejected() -> None:
    """当成「从头开始」的话，客户端会收到一整页重复数据而看不出发生了什么。"""
    with pytest.raises(CursorError):
        decode("不是游标")


def test_a_cursor_without_the_identifier_is_rejected() -> None:
    with pytest.raises(CursorError):
        decode(encode(datetime.now(UTC), uuid4())[:8])


def test_a_full_page_reports_more_to_come() -> None:
    page, has_more = split([1, 2, 3, 4], 3)

    assert page == [1, 2, 3]
    assert has_more is True


def test_a_short_page_is_the_last_one() -> None:
    page, has_more = split([1, 2], 3)

    assert page == [1, 2]
    assert has_more is False


def test_an_empty_result_is_the_last_page() -> None:
    assert split([], 3) == ([], False)
