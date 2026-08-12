"""取消端点的测试。

**这里验的是「api 那一半」**：立标志、抢状态、推事件、回真实状态。worker 在 step
边界上收手那一半在 `test/run/executor_test.py`，两边共用的原子性在
`test/run/repository_test.py`。
"""

from functools import partial
from uuid import uuid4

from fastapi.testclient import TestClient
from redis.asyncio import Redis

from api.platform import Platform
from event.model import EventType, RunStatus
from run.cancel import KEY_PREFIX
from test.api.conftest import Agent, drain


def test_cancelling_a_running_run_turns_it_cancelled(client: TestClient, agent: Agent, thread_id: str) -> None:
    run_id = _submit(client, thread_id, agent)

    response = client.post(f"/api/runs/{run_id}/cancel")

    assert response.status_code == 202
    assert response.json()["status"] == RunStatus.CANCELLED.value


def test_cancelling_raises_the_flag_the_worker_reads(
    client: TestClient, agent: Agent, thread_id: str, live_cache: Redis
) -> None:
    """标志是 api 与 worker 之间唯一的取消通道 —— 它们在两个进程里。"""
    run_id = _submit(client, thread_id, agent)
    assert client.portal is not None

    client.post(f"/api/runs/{run_id}/cancel")

    assert client.portal.call(partial(live_cache.exists, f"{KEY_PREFIX}{run_id}")) == 1


def test_cancelling_pushes_a_run_cancelled_event(client: TestClient, agent: Agent, thread_id: str) -> None:
    run_id = _submit(client, thread_id, agent)

    client.post(f"/api/runs/{run_id}/cancel")

    assert any(EventType.RUN_CANCELLED.value in line for line in drain(client, run_id))


def test_the_status_endpoint_agrees(client: TestClient, agent: Agent, thread_id: str) -> None:
    run_id = _submit(client, thread_id, agent)

    client.post(f"/api/runs/{run_id}/cancel")

    assert client.get(f"/api/runs/{run_id}").json()["status"] == RunStatus.CANCELLED.value


def test_cancelling_twice_is_not_an_error(client: TestClient, agent: Agent, thread_id: str) -> None:
    """教师会连点两下「停止」。"""
    run_id = _submit(client, thread_id, agent)

    first = client.post(f"/api/runs/{run_id}/cancel")
    second = client.post(f"/api/runs/{run_id}/cancel")

    assert first.status_code == 202
    assert second.status_code == 202


def test_cancelling_twice_pushes_only_one_event(client: TestClient, agent: Agent, thread_id: str) -> None:
    """条件更新是原子的，只有改成了的那一次才推事件 —— 否则教师看到两次「已取消」。"""
    run_id = _submit(client, thread_id, agent)

    client.post(f"/api/runs/{run_id}/cancel")
    client.post(f"/api/runs/{run_id}/cancel")

    # 一条事件在 SSE 里是好几行，只数 `event:` 那一行
    cancelled = [line for line in drain(client, run_id) if line == f"event: {EventType.RUN_CANCELLED.value}"]
    assert len(cancelled) == 1


def test_cancelling_a_finished_run_does_not_rewrite_it(client: TestClient, agent: Agent, thread_id: str) -> None:
    """已经跑完的那一次并没有被取消，谎报会让前端把一次成功的分析显示成被中断。"""
    run_id = _submit(client, thread_id, agent, blocked=False)
    drain(client, run_id)

    response = client.post(f"/api/runs/{run_id}/cancel")

    assert response.status_code == 202
    assert response.json()["status"] == RunStatus.SUCCEEDED.value


def test_an_unknown_run_cannot_be_cancelled(client: TestClient) -> None:
    assert client.post(f"/api/runs/{uuid4().hex}/cancel").status_code == 404


def test_a_cancelled_run_frees_its_concurrency_slot(
    client: TestClient, agent: Agent, platform: Platform, thread_id: str
) -> None:
    """取消之后名额要还回来 —— 不还的话，取消反而把自己锁得更死。"""
    run_id = _submit(client, thread_id, agent)
    assert client.portal is not None
    identity = client.get("/api/auth/me").json()["id"]

    client.post(f"/api/runs/{run_id}/cancel")

    assert client.portal.call(partial(platform.usage.active_run, identity)) == 0


def _submit(client: TestClient, thread_id: str, agent: Agent, *, blocked: bool = True) -> str:
    """提交一次分析，默认把 agent 卡住。

    **不卡住就没得取消**：假 agent 转眼跑完，请求还没发出去 run 已经是终态了。
    """
    agent.blocked = blocked
    identifier: str = client.post(f"/api/threads/{thread_id}/runs", json={"content": "算个波动率"}).json()["id"]
    return identifier
