"""记忆 catalog、正文、选择 snapshot 与依赖边界。"""

from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, ConfigDict, Field

from app.event.model import TokenUsage


class MemoryType(StrEnum):
    """会话私有记忆的业务类型。"""

    USER = "user"
    FEEDBACK = "feedback"
    PROJECT = "project"
    REFERENCE = "reference"


class MemoryCatalogEntry(BaseModel):
    """短索引中的一条元数据，刻意不含正文。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    slug: str = Field(min_length=1, description="thread 内稳定的记忆标识")
    name: str = Field(min_length=1, description="给人阅读的名称")
    description: str = Field(min_length=1, description="供选择器判断相关性的短描述")
    type: MemoryType = Field(description="记忆的业务类型")
    updated_at: datetime = Field(description="最后更新时间")


class MemoryRecord(MemoryCatalogEntry):
    """被选中后才从记忆服务读取的完整记忆。"""

    body: str = Field(min_length=1, description="Markdown 正文")


class SelectionFallback(StrEnum):
    """辅助模型选择未被采用的可审计原因。"""

    INVALID_OUTPUT = "invalid_output"
    DUPLICATE_INDEX = "duplicate_index"
    OUT_OF_RANGE = "out_of_range"
    TIMEOUT = "timeout"
    MODEL_ERROR = "model_error"
    SERVICE_ERROR = "service_error"


class MemorySelection(BaseModel):
    """一次 catalog 选择的结果。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    indices: tuple[int, ...] = Field(default=(), description="catalog 的零基索引")
    fallback: SelectionFallback | None = Field(default=None, description="关键词回退原因")
    usage: TokenUsage = Field(default_factory=TokenUsage, description="本次选择器模型调用的 token")
    duration_ms: int = Field(default=0, ge=0, description="选择器调用及协议解析耗时")


class MemorySnapshot(BaseModel):
    """同一 run 内固定复用的召回结果。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=1, description="snapshot 所属 run")
    thread_id: str = Field(min_length=1, description="记忆所属 thread")
    records: tuple[MemoryRecord, ...] = Field(default=(), description="已通过正文预算的记忆")
    selected_indices: tuple[int, ...] = Field(default=(), description="预算之前选中的 catalog 索引")
    selected_slugs: tuple[str, ...] = Field(default=(), description="预算之前选中的可审计 slug")
    fallback: SelectionFallback | None = Field(default=None, description="选择或服务降级原因")
    selector_usage: TokenUsage = Field(default_factory=TokenUsage, description="选择器分项 token 账")
    selector_duration_ms: int = Field(default=0, ge=0, description="选择器耗时")


class MemoryServiceProtocol(Protocol):
    """只读记忆服务边界；具体 HTTP 客户端由运行时提供。"""

    async def catalog(self, thread_id: str) -> Sequence[MemoryCatalogEntry]:
        """读取指定 thread 的短索引。"""
        ...

    async def read(self, thread_id: str, slugs: tuple[str, ...]) -> Sequence[MemoryRecord]:
        """只读取已选中 slug 的正文。"""
        ...


class SelectorModelProtocol(Protocol):
    """轻量选择模型的最小异步边界。"""

    async def ainvoke(self, prompt: str, config: RunnableConfig | None = None) -> AIMessage:
        """根据 catalog 与近期问题返回索引数组。"""
        ...


class UsageCallbackProtocol(Protocol):
    """把 selector 用量并入当前 run 的受控回调。"""

    def __call__(self, usage: TokenUsage) -> None:
        """记录一次 selector 模型调用。"""
        ...
