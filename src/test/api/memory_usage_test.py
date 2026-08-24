"""评测读取 run 级记忆分项账的 API 测试。"""

from functools import partial
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.platform import Platform
from app.event.model import TokenUsage
from app.memory.job import MemoryJobPayload, MemoryJobRepository, MemoryUsage, MemoryUsageStage


def _create_run(client: TestClient, platform: Platform, thread_id: str) -> tuple[str, str]:
    """为当前登录用户建立一条不会被测试 worker 领取的 run。"""
    user_id = str(client.get("/api/auth/me").json()["id"])
    run_id = uuid4().hex
    assert client.portal is not None
    client.portal.call(
        partial(
            platform.repository.create,
            run_id=run_id,
            thread_id=thread_id,
            user_id=user_id,
        )
    )
    return run_id, user_id


def test_missing_memory_ledger_stays_null_instead_of_becoming_zero(
    client: TestClient,
    platform: Platform,
    thread_id: str,
) -> None:
    run_id, _ = _create_run(client, platform, thread_id)

    response = client.get(f"/api/runs/{run_id}/memory-usage")

    assert response.status_code == 200
    assert response.json() == {
        "job_status": None,
        "selector": None,
        "extractor": None,
        "consolidator": None,
    }


def test_memory_ledger_returns_job_status_and_all_three_stages(
    client: TestClient,
    platform: Platform,
    thread_id: str,
) -> None:
    run_id, user_id = _create_run(client, platform, thread_id)
    repository = MemoryJobRepository(platform.engine)
    assert client.portal is not None
    client.portal.call(partial(platform.repository.start, run_id))
    created = client.portal.call(
        partial(
            platform.repository.succeed,
            run_id,
            tokens=TokenUsage(),
            memory_job=MemoryJobPayload(
                thread_id=thread_id,
                user_id=user_id,
                messages=[{"role": "user", "content": "记住我的口径"}],
            ),
        )
    )
    assert created is True
    usages = (
        MemoryUsage(
            run_id=run_id,
            thread_id=thread_id,
            stage=MemoryUsageStage.SELECTOR,
            model="selector-model",
            tokens=TokenUsage(input_cache_read=1, input_uncached=2, output=3),
            cost_yuan=0.12,
            duration_ms=45,
            hit_count=2,
            included_in_run=True,
            selected_slugs=("risk-preference", "project-rule"),
        ),
        # 这一项是**显式零账**，必须与没有记录的 null 区分。
        MemoryUsage(
            run_id=run_id,
            thread_id=thread_id,
            stage=MemoryUsageStage.EXTRACTOR,
            model="extractor-model",
            tokens=TokenUsage(),
            cost_yuan=0.0,
            duration_ms=0,
            fallback_reason="no_candidate",
        ),
        MemoryUsage(
            run_id=run_id,
            thread_id=thread_id,
            stage=MemoryUsageStage.CONSOLIDATOR,
            model="consolidator-model",
            tokens=TokenUsage(input_uncached=5, output=1),
            cost_yuan=0.08,
            duration_ms=70,
            hit_count=1,
            rejected_count=2,
        ),
    )
    for usage in usages:
        client.portal.call(partial(repository.record_usage, usage))

    response = client.get(f"/api/runs/{run_id}/memory-usage")

    assert response.status_code == 200
    payload = response.json()
    assert payload["job_status"] == "queued"
    assert all(payload[stage] is not None for stage in ("selector", "extractor", "consolidator"))
    assert payload["selector"] == {
        "model": "selector-model",
        "tokens_cache_read": 1,
        "tokens_uncached": 2,
        "tokens_output": 3,
        "cost_yuan": 0.12,
        "duration_ms": 45,
        "hit_count": 2,
        "rejected_count": 0,
        "fallback_reason": None,
        "included_in_run": True,
        "selected_slugs": ["risk-preference", "project-rule"],
    }
    assert payload["extractor"] == {
        "model": "extractor-model",
        "tokens_cache_read": 0,
        "tokens_uncached": 0,
        "tokens_output": 0,
        "cost_yuan": 0.0,
        "duration_ms": 0,
        "hit_count": 0,
        "rejected_count": 0,
        "fallback_reason": "no_candidate",
        "included_in_run": False,
        "selected_slugs": [],
    }
    assert payload["consolidator"] == {
        "model": "consolidator-model",
        "tokens_cache_read": 0,
        "tokens_uncached": 5,
        "tokens_output": 1,
        "cost_yuan": 0.08,
        "duration_ms": 70,
        "hit_count": 1,
        "rejected_count": 2,
        "fallback_reason": None,
        "included_in_run": False,
        "selected_slugs": [],
    }
