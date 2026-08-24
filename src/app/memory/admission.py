"""记忆候选的严格 schema、slug 生成与确定性准入门禁。"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.memory.model import MemoryType
from app.memory.store import MemoryRecord

_CANDIDATE_FIELD = frozenset({"scope", "name", "description", "type", "content"})
_SLUG_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_SLUG_PART_PATTERN = re.compile(r"[^a-z0-9]+")
_MAX_SLUG_LENGTH = 96

_TEMPORARY_MARKER = (
    "this session",
    "current session",
    "this turn",
    "current turn",
    "this task",
    "current task",
    "for now",
    "just this time",
    "today only",
    "本次会话",
    "当前会话",
    "这一轮",
    "本轮",
    "当前轮次",
    "本次任务",
    "这次任务",
    "当前任务",
    "仅限本次",
    "暂时",
    "临时限制",
)
_TEMPORARY_PATH_PATTERN = re.compile(
    r"(?i)(?:/tmp/|/var/tmp/|/workspace/(?:uploads?|tmp)/|[a-z]:\\(?:temp|tmp)\\|(?:^|[\s/])tmp/)"
)
_TOOL_OUTPUT_PATTERN = re.compile(
    r"(?is)(?:<tool_result>|\"type\"\s*:\s*\"tool_result\"|"
    r"(?:stdout|stderr|exit\s+code|return\s+code|tool\s+(?:output|result|call))\s*[:=]|"
    r"(?:工具输出|工具结果|工具调用|命令输出)[:：])"
)
_ASSUMPTION_PATTERN = re.compile(
    r"(?is)(?:(?:助手|模型|我)(?:猜测|推测|假设|估计|认为)|"
    r"未经用户确认|尚未核实|(?:the\s+)?assistant\s+(?:assumes?|guesses?|thinks?|suspects?))"
)
_SECRET_PATTERN = re.compile(
    r"(?is)(?:"
    r"(?:password|passwd|api[\s_-]?key|secret(?:[\s_-]?key)?|access[\s_-]?token|"
    r"refresh[\s_-]?token|github[\s_-]?token|token)\s*[:=]\s*[^\s,;]{4,}|"
    r"(?:密码|密钥|令牌|凭据)\s*[：:=]\s*\S{4,}|"
    r"authorization\s*:\s*bearer\s+\S+|"
    r"\bsk-[a-z0-9_-]{10,}|\bAKIA[A-Z0-9]{16}\b|\bgh[pousr]_[A-Za-z0-9]{20,}|"
    r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+|"
    r"-----BEGIN(?: [A-Z]+)? PRIVATE KEY-----)"
)
_INJECTION_PATTERN = re.compile(
    r"(?is)(?:"
    r"忽略.{0,20}(?:系统|平台|之前|上面).{0,20}(?:指令|规则|提示)|"
    r"(?:绕过|跳过).{0,20}(?:审批|权限|沙箱|配额|系统|平台)|"
    r"ignore.{0,30}(?:previous|system|platform).{0,30}(?:instructions?|rules?|prompts?)|"
    r"system\s+prompt|act\s+as\s+(?:root|admin|system)|"
    r"</?(?:agent_memory|system|system-reminder)\b)"
)


class CandidateScope(StrEnum):
    """辅助模型对候选有效期的声明。"""

    PERSISTENT = "persistent"
    CURRENT_TASK = "current_task"


class MemoryCandidate(BaseModel):
    """辅助模型必须严格返回的候选形状。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scope: CandidateScope
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    type: MemoryType
    content: str = Field(min_length=1)

    @field_validator("name", "description", "content")
    @classmethod
    def _clean_text(cls, value: str, info: object) -> str:
        """去除模型多吐的首尾空白，阻止 frontmatter 字段换行。"""
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("记忆候选字段不能为空")
        field_name = getattr(info, "field_name", "")
        if field_name in {"name", "description"} and "\n" in cleaned:
            raise ValueError("记忆 name 与 description 不能换行")
        if "\x00" in cleaned:
            raise ValueError("记忆候选不能包含空字节")
        return cleaned


class AdmissionRejection(StrEnum):
    """候选未进入活动 memdir 的稳定审计原因。"""

    CURRENT_TASK = "current_task"
    INCOMPLETE_FIELDS = "incomplete_fields"
    INVALID_SCHEMA = "invalid_schema"
    TEMPORARY = "temporary"
    TOOL_OUTPUT = "tool_output"
    ASSISTANT_ASSUMPTION = "assistant_assumption"
    DUPLICATE = "duplicate"
    SECRET = "secret"
    INSTRUCTION_INJECTION = "instruction_injection"


@dataclass(frozen=True)
class AdmissionDecision:
    """一条候选的准入结果；拒绝时不保留原始正文。"""

    record: MemoryRecord | None
    reason: AdmissionRejection | None


def admit_candidate(raw: object, *, existing: Sequence[MemoryRecord]) -> AdmissionDecision:
    """校验一条模型候选，通过后转成 `MemoryStore.write` 可直接接收的记录。"""
    candidate, invalid_reason = _candidate(raw)
    if candidate is None:
        return AdmissionDecision(record=None, reason=invalid_reason)
    if candidate.scope is CandidateScope.CURRENT_TASK:
        return AdmissionDecision(record=None, reason=AdmissionRejection.CURRENT_TASK)

    text = _normalized(f"{candidate.name}\n{candidate.description}\n{candidate.content}")
    if any(marker in text for marker in _TEMPORARY_MARKER) or _TEMPORARY_PATH_PATTERN.search(text):
        return AdmissionDecision(record=None, reason=AdmissionRejection.TEMPORARY)
    if _TOOL_OUTPUT_PATTERN.search(text):
        return AdmissionDecision(record=None, reason=AdmissionRejection.TOOL_OUTPUT)
    if _ASSUMPTION_PATTERN.search(text):
        return AdmissionDecision(record=None, reason=AdmissionRejection.ASSISTANT_ASSUMPTION)
    if _SECRET_PATTERN.search(text):
        return AdmissionDecision(record=None, reason=AdmissionRejection.SECRET)
    if _INJECTION_PATTERN.search(text):
        return AdmissionDecision(record=None, reason=AdmissionRejection.INSTRUCTION_INJECTION)

    slug = memory_slug(candidate.name)
    if _is_duplicate(slug, candidate, existing):
        return AdmissionDecision(record=None, reason=AdmissionRejection.DUPLICATE)
    return AdmissionDecision(
        record=MemoryRecord(
            slug=slug,
            name=candidate.name,
            description=candidate.description,
            type=candidate.type.value,
            content=candidate.content,
        ),
        reason=None,
    )


def memory_slug(name: str) -> str:
    """把任意语言的名称转成稳定、ASCII 且可作文件名的 slug。"""
    normalized = unicodedata.normalize("NFKD", name).casefold()
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    base = _SLUG_PART_PATTERN.sub("-", ascii_name).strip("-")
    digest = hashlib.sha256(unicodedata.normalize("NFKC", name).encode()).hexdigest()[:16]
    if not base:
        base = f"memory-{digest}"
    elif len(base) > _MAX_SLUG_LENGTH:
        base = f"{base[: _MAX_SLUG_LENGTH - 17].rstrip('-')}-{digest}"
    if _SLUG_PATTERN.fullmatch(base) is None:
        raise ValueError("生成的记忆 slug 不合法")
    return base


def _candidate(raw: object) -> tuple[MemoryCandidate | None, AdmissionRejection | None]:
    """区分缺字段与字段形状错误，便于审计。"""
    if not isinstance(raw, dict):
        return None, AdmissionRejection.INVALID_SCHEMA
    missing = _CANDIDATE_FIELD - raw.keys()
    if missing:
        return None, AdmissionRejection.INCOMPLETE_FIELDS
    for field in _CANDIDATE_FIELD:
        value = raw[field]
        if value is None or (isinstance(value, str) and not value.strip()):
            return None, AdmissionRejection.INCOMPLETE_FIELDS
    try:
        return MemoryCandidate.model_validate(raw), None
    except ValidationError:
        return None, AdmissionRejection.INVALID_SCHEMA


def _is_duplicate(slug: str, candidate: MemoryCandidate, existing: Sequence[MemoryRecord]) -> bool:
    """名称 slug、描述或正文任一完全相同即视为重复。"""
    description = _normalized(candidate.description)
    content = _normalized(candidate.content)
    return any(
        record.slug == slug or _normalized(record.description) == description or _normalized(record.content) == content
        for record in existing
    )


def _normalized(value: str) -> str:
    """做重复、标记匹配用的 Unicode/空白归一化。"""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())
