"""从记忆短索引选出与近期用户问题相关的记忆。"""

import asyncio
import json
import logging
import re
import time
from collections.abc import Mapping, Sequence

from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.constants import TAG_NOSTREAM

from app.agent.tail import BLOCK_HEADER
from app.event.model import TokenUsage
from app.memory.model import (
    MemoryCatalogEntry,
    MemorySelection,
    SelectionFallback,
    SelectorModelProtocol,
    UsageCallbackProtocol,
)

logger = logging.getLogger(__name__)

MAX_SELECTED_MEMORY = 5
RECENT_USER_MESSAGE_LIMIT = 3
SELECTOR_TIMEOUT_SECOND = 15.0

_ASCII_TERM_PATTERN = re.compile(r"[a-z0-9_]+")
_CHINESE_RUN_PATTERN = re.compile(r"[\u4e00-\u9fff]+")


class SelectionParseError(ValueError):
    """辅助模型的输出不是合法索引数组。"""

    def __init__(self, reason: SelectionFallback) -> None:
        super().__init__(reason.value)
        self.reason = reason


def parse_indices(raw: str, *, catalog_size: int) -> tuple[int, ...]:
    """严格解析一个最多五项的零基 JSON 索引数组。

    不接受 Markdown 代码栏、对象包装、字符串数字或布尔值；这些宽容
    会让模型升级后的协议偏移静默进入生产。

    Args:
        raw: 辅助模型原始文字。
        catalog_size: 当次 catalog 条数。

    Returns:
        经校验的索引元组。

    Raises:
        SelectionParseError: 格式、数量、重复或边界不合法。
    """
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise SelectionParseError(SelectionFallback.INVALID_OUTPUT) from exc
    if not isinstance(parsed, list) or len(parsed) > MAX_SELECTED_MEMORY:
        raise SelectionParseError(SelectionFallback.INVALID_OUTPUT)
    if any(type(index) is not int for index in parsed):
        raise SelectionParseError(SelectionFallback.INVALID_OUTPUT)
    indices = tuple(parsed)
    if len(set(indices)) != len(indices):
        raise SelectionParseError(SelectionFallback.DUPLICATE_INDEX)
    if any(index < 0 or index >= catalog_size for index in indices):
        raise SelectionParseError(SelectionFallback.OUT_OF_RANGE)
    return indices


def recent_user_messages(messages: Sequence[BaseMessage]) -> tuple[str, ...]:
    """取最近三条真实用户消息，排除平台持久追加的尾部块。"""
    genuine: list[str] = []
    for message in messages:
        if not isinstance(message, HumanMessage) or not isinstance(message.content, str):
            continue
        content = message.content.strip()
        if not content or content.startswith(BLOCK_HEADER):
            continue
        genuine.append(content)
    return tuple(genuine[-RECENT_USER_MESSAGE_LIMIT:])


class MemorySelector:
    """优先用辅助模型选 catalog，协议异常时做确定性关键词回退。

    Args:
        model: 只接收短 catalog 的轻量模型。
        usage: 把这次额外模型用量并入主 run 的回调。
        timeout_second: 单次选择的超时秒数。
    """

    def __init__(
        self,
        *,
        model: SelectorModelProtocol,
        usage: UsageCallbackProtocol | None = None,
        timeout_second: float = SELECTOR_TIMEOUT_SECOND,
    ) -> None:
        if timeout_second <= 0:
            raise ValueError("选择器超时必须大于 0 秒")
        self._model = model
        self._usage = usage
        self._timeout_second = timeout_second

    async def select(
        self,
        catalog: Sequence[MemoryCatalogEntry],
        messages: Sequence[BaseMessage],
    ) -> MemorySelection:
        """从 catalog 选出最多五项，任何模型协议问题都回退关键词。"""
        if not catalog:
            return MemorySelection()
        recent = recent_user_messages(messages)
        prompt = _selector_prompt(catalog, recent)
        started = time.monotonic_ns()
        usage = TokenUsage()
        try:
            async with asyncio.timeout(self._timeout_second):
                response = await self._model.ainvoke(prompt, config={"tags": [TAG_NOSTREAM]})
            usage = _token_usage(response.usage_metadata)
            if self._usage is not None:
                self._usage(usage)
            if not isinstance(response.content, str):
                raise SelectionParseError(SelectionFallback.INVALID_OUTPUT)
            return MemorySelection(
                indices=parse_indices(response.content, catalog_size=len(catalog)),
                usage=usage,
                duration_ms=_elapsed_ms(started),
            )
        except TimeoutError:
            reason = SelectionFallback.TIMEOUT
            logger.warning("selector 超时，改用关键词匹配")
        except SelectionParseError as exc:
            reason = exc.reason
            logger.info("selector 输出不合法，改用关键词匹配：reason=%s", reason.value)
        except Exception:
            # 辅助模型是降级边界：它的 SDK/回调异常不应吞掉教师的主分析。
            reason = SelectionFallback.MODEL_ERROR
            logger.warning("selector 调用失败，改用关键词匹配", exc_info=True)
        return MemorySelection(
            indices=_keyword_indices(catalog, recent),
            fallback=reason,
            usage=usage,
            duration_ms=_elapsed_ms(started),
        )


def _selector_prompt(catalog: Sequence[MemoryCatalogEntry], recent: tuple[str, ...]) -> str:
    """构造只含短索引与最近三问的严格选择协议。"""
    entries = [
        {
            "index": index,
            "slug": entry.slug,
            "name": entry.name,
            "description": entry.description,
            "type": entry.type.value,
            "updated_at": entry.updated_at.isoformat(),
        }
        for index, entry in enumerate(catalog)
    ]
    return "\n".join(
        (
            "你是会话记忆选择器。根据最近用户问题，从 catalog 选最多 5 条相关记忆。",
            "只返回零基索引的 JSON 数组，例如 [2,0]；无相关记忆返回 []，不要返回其他文字。",
            f"catalog={json.dumps(entries, ensure_ascii=False, separators=(',', ':'))}",
            f"最近用户问题={json.dumps(recent, ensure_ascii=False, separators=(',', ':'))}",
        )
    )


def _keyword_indices(catalog: Sequence[MemoryCatalogEntry], recent: tuple[str, ...]) -> tuple[int, ...]:
    """用中英文词与中文双字组重叠做稳定、可重放的降级选择。"""
    query_terms = _terms("\n".join(recent))
    if not query_terms:
        return ()
    ranked: list[tuple[int, str, str, str, int]] = []
    for index, entry in enumerate(catalog):
        score = len(query_terms & _terms(f"{entry.name}\n{entry.description}"))
        if score:
            ranked.append((-score, entry.description.casefold(), entry.updated_at.isoformat(), entry.slug, index))
    ranked.sort()
    return tuple(item[-1] for item in ranked[:MAX_SELECTED_MEMORY])


def _terms(text: str) -> set[str]:
    """生成关键词回退的粗粒度词集。"""
    lowered = text.casefold()
    terms = {term for term in _ASCII_TERM_PATTERN.findall(lowered) if len(term) >= 2}
    for run in _CHINESE_RUN_PATTERN.findall(lowered):
        if len(run) == 1:
            continue
        terms.update(run[index : index + 2] for index in range(len(run) - 1))
    return terms


def _token_usage(metadata: Mapping[str, object] | None) -> TokenUsage:
    """把 LangChain 的 input 总数拆成 cache 命中与未命中两部分。"""
    if metadata is None:
        return TokenUsage()
    detail = metadata.get("input_token_details")
    cache_read = _as_int(detail.get("cache_read")) if isinstance(detail, dict) else 0
    input_total = _as_int(metadata.get("input_tokens"))
    return TokenUsage(
        input_cache_read=cache_read,
        input_uncached=max(0, input_total - cache_read),
        output=_as_int(metadata.get("output_tokens")),
    )


def _elapsed_ms(started_ns: int) -> int:
    """单调时钟换算成非负毫秒；极快调用允许为零。"""
    return max(0, (time.monotonic_ns() - started_ns) // 1_000_000)


def _as_int(value: object) -> int:
    """非负整数计数以外的异常形状按零处理。"""
    return value if isinstance(value, int) and value >= 0 else 0
