"""翻页游标的编解码。

**列表一律用游标而不是 offset。** 会话按 `updated_at DESC` 排，而这个字段会因为新提问
而变动：翻页途中若有会话被顶到首页，offset 分页会漏掉或重复条目，且不报错。游标记的是
「上一页最后那一条是谁」，中间怎么变都不会错位。

游标是**不透明的**：调用方只该原样回传。里面是 `(时间, 标识)` 复合值 —— 只用时间的话，
同一毫秒提交的两条会在翻页边界上互相顶掉。

解析不了的游标要**明确拒绝**，不能当成「从头开始」：那会让客户端收到一整页重复数据，
而它看不出发生了什么。
"""

from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

# 一页最多给多少条。**上限不是口味问题**：会话列表一条几十字节，但 run 列表带着提问原文，
# 放开的话一次请求就能把整个会话的历史全拉出来
MAX_PAGE_SIZE = 100

DEFAULT_PAGE_SIZE = 20

SEPARATOR = "|"

ENCODING = "utf-8"


class CursorError(ValueError):
    """游标不合法。

    它来自查询参数，属于不可信输入 —— 对外的回答是 422，不是 500。
    """


@dataclass(frozen=True)
class Page[Item]:
    """一页数据，以及取下一页要带的游标。

    `next_cursor` 为空表示到底了 —— 前端据此停止「加载更多」。
    """

    items: list[Item]
    next_cursor: str | None


def encode(when: datetime, identifier: UUID) -> str:
    """把一条记录的位置编成游标。

    Args:
        when: 排序用的时间。
        identifier: 同一时刻的并列项之间的次序。

    Returns:
        可放进查询参数的不透明字符串。
    """
    raw = f"{when.isoformat()}{SEPARATOR}{identifier.hex}"
    return urlsafe_b64encode(raw.encode(ENCODING)).decode(ENCODING)


def decode(cursor: str) -> tuple[datetime, UUID]:
    """把游标还原成位置。

    Args:
        cursor: 上一页给的游标。

    Returns:
        (时间, 标识)。

    Raises:
        CursorError: 格式不合法。
    """
    try:
        raw = urlsafe_b64decode(cursor.encode(ENCODING)).decode(ENCODING)
        when, separator, identifier = raw.partition(SEPARATOR)
        if not separator:
            raise ValueError(raw)
        return datetime.fromisoformat(when), UUID(identifier)
    # base64、utf-8、时间与 uuid 四段各有各的异常类型，而对调用方它们是同一件事
    except (ValueError, TypeError) as exc:
        message = f"游标不合法：{cursor!r}"
        raise CursorError(message) from exc


def split[Record](found: list[Record], limit: int) -> tuple[list[Record], bool]:
    """把「多查了一条」的结果切成一页，并回答还有没有下一页。

    多查一条是判断「到底了没」的唯一可靠办法 —— 按总数算要多一次 `count(*)`，
    而那两次查询之间数据还会变。

    Args:
        found: 查询结果，条数上限应为 `limit + 1`。
        limit: 一页几条。

    Returns:
        (这一页, 后面还有没有)。
    """
    return found[:limit], len(found) > limit
