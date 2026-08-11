"""会话工作目录的浏览：列出目录树、预览文件内容。

**这是给教师看的，不是给 agent 看的。** agent 的七个文件工具走 `SandboxBackend`，
路径带 `/workspace` 前缀、结果按 LLM 的口味排布；这里的路径相对会话根
（`outputs/chart.png`），形状按侧边栏的需要来。

**预览不复用框架的 `read`**，两个原因都会当场伤到教师：它按**扩展名**判文本还是二进制，
`.pkl` 这类没登记的扩展名会走文本分支然后解码失败；而且它**整个文件读进内存之后才分页**，
点开一个 200MB 的 csv 就是 200MB。这里按内容判类型，且只读开头一截。

**越界防护不在本模块**：路径解析与前缀校验由 `Workspace` 做完，这里拿到的已经是
确认落在会话目录内的真实路径。本模块只负责「不把符号链接列进树里」——
那是防护的另一半，纯路径校验看不见它。
"""

import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import islice
from pathlib import Path

logger = logging.getLogger(__name__)

# 一棵树最多给多少个条目。agent 在 5GB 配额之内造得出上万个小文件，
# 整棵发出去既拖垮浏览器又没人看得完
MAX_ENTRY = 2000

# 预览最多读多少字节。1 MiB 已经是几万行代码，再多就不是「看一眼」而是下载了
PREVIEW_MAX_BYTE = 1 << 20

# 预览一屏给多少行
DEFAULT_PREVIEW_LINE = 500

# 一个 UTF-8 字符最多几个字节。截断读会切在字符中间，末尾至多丢这么多
MAX_UTF8_WIDTH = 4


@dataclass(frozen=True)
class Entry:
    """目录树里的一个条目。"""

    path: str
    is_dir: bool
    size: int
    modified_at: datetime


@dataclass(frozen=True)
class Tree:
    """一个会话工作目录的全部条目。"""

    entries: list[Entry]
    # 条目太多被砍过。**砍掉的是任意一批**：超限时不再全量排序，
    # 那正是要避免的开销。前端据此提示「文件太多，只显示前 N 个」
    truncated: bool


@dataclass(frozen=True)
class Preview:
    """一个文件的一段文本内容。"""

    text: str
    # 读到的总行数。**截断时它只是开头那一截的行数**，不是文件的真实行数 ——
    # 要知道真实行数就得读完整个文件，而那正是这里在避免的事
    total_line: int
    # 1-indexed 的窗口边界，窗口为空时都是 0
    start_line: int
    end_line: int
    is_binary: bool
    # 文件比字节上限长，后面还有没读的
    truncated: bool


def tree(root: Path, *, limit: int = MAX_ENTRY) -> Tree:
    """列出一个会话工作目录下的全部条目。

    目录也在结果里 —— 侧边栏要显示空的 `outputs/`，只列文件的话它就不存在。

    **符号链接一个都不列，也不走进去。** agent 在沙箱里建得出链接，列进树里
    就等于把宿主机上的任意文件摆上货架，而它下一步就是可下载的。

    Args:
        root: 会话的工作目录。
        limit: 最多给多少个条目，超出即截断。

    Returns:
        按路径排序的条目，以及有没有被截断。
    """
    # 先过滤再截断：符号链接不该占掉名额。`rglob` 本身不跟随链接目录（3.13 起的默认），
    # 这里再挡一次链接文件本身
    walking = (path for path in root.rglob("*") if not path.is_symlink())
    found = list(islice(walking, limit + 1))
    entries = [one for one in (_describe(root, path) for path in found[:limit]) if one is not None]
    entries.sort(key=lambda one: one.path)
    return Tree(entries=entries, truncated=len(found) > limit)


def preview(
    target: Path,
    *,
    offset: int = 0,
    limit: int = DEFAULT_PREVIEW_LINE,
    max_byte: int = PREVIEW_MAX_BYTE,
) -> Preview:
    """把一个文件的开头一截当文本读出来。

    Args:
        target: 会话目录内的文件。
        offset: 从第几行开始，0-indexed，负数按 0 算。
        limit: 最多给多少行。
        max_byte: 最多读多少字节。

    Returns:
        窗口内的文本；文件不是文本时 `is_binary` 为真、`text` 为空，
        调用方该改用原始字节那条路。

    Raises:
        OSError: 文件读不了。
    """
    with target.open("rb") as opened:
        # 多读一个字节才分得清「正好读满」与「后面还有」
        raw = opened.read(max_byte + 1)
    truncated = len(raw) > max_byte
    text = _decode(raw[:max_byte], truncated=truncated)
    if text is None:
        return Preview(text="", total_line=0, start_line=0, end_line=0, is_binary=True, truncated=truncated)

    line = text.splitlines()
    start = max(offset, 0)
    window = line[start : start + limit] if limit > 0 else []
    return Preview(
        text="\n".join(window),
        total_line=len(line),
        start_line=start + 1 if window else 0,
        end_line=start + len(window) if window else 0,
        is_binary=False,
        truncated=truncated,
    )


def _describe(root: Path, path: Path) -> Entry | None:
    """量一个条目。量不了就当它不存在。

    走到一半文件被 agent 删掉是正常的 —— 这个进程在读，沙箱里那个还在跑。
    为此让整次列目录失败不划算。
    """
    try:
        stat = path.stat()
    except OSError:
        logger.debug("列目录时这个条目读不到，跳过：%s", path, exc_info=True)
        return None
    return Entry(
        path=path.relative_to(root).as_posix(),
        is_dir=os.path.isdir(path),
        size=stat.st_size,
        modified_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
    )


def _decode(raw: bytes, *, truncated: bool) -> str | None:
    """把字节解成 UTF-8 文本，解不出来就当它是二进制。

    截断读会把末尾那个多字节字符切成半个，直接判「解不出来即二进制」会把
    整个中文文件判错，因此末尾允许丢掉至多一个字符的宽度再试。
    """
    if b"\x00" in raw:
        return None
    droppable = MAX_UTF8_WIDTH - 1 if truncated else 0
    for drop in range(droppable + 1):
        try:
            return raw[: len(raw) - drop].decode("utf-8")
        except UnicodeDecodeError:
            continue
    return None
