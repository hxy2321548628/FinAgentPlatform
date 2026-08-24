"""记忆召回的数据形状测试。"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.memory.model import MemoryCatalogEntry, MemoryRecord, MemoryType


def test_catalog_entry_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        MemoryCatalogEntry.model_validate(
            {
                "slug": "risk-preference",
                "name": "风险偏好",
                "description": "教师偏好的风险表达方式",
                "type": MemoryType.USER,
                "updated_at": datetime(2026, 8, 21, tzinfo=UTC),
                "body": "catalog 不得夹带正文",
            }
        )


def test_memory_record_is_immutable() -> None:
    record = MemoryRecord(
        slug="risk-preference",
        name="风险偏好",
        description="教师偏好的风险表达方式",
        type=MemoryType.USER,
        updated_at=datetime(2026, 8, 21, tzinfo=UTC),
        body="先给结论，再解释波动来源。",
    )

    with pytest.raises(ValidationError):
        record.body = "被静默篡改"  # type: ignore[misc]
