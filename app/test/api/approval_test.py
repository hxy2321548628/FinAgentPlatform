"""审批端点的测试：四种决策各走一遍，加上 index 校验与两道防堆积的闸。

**四种决策都要验**：它们在 DeepAgents 侧是四条不同的恢复路径，只验 `approve`
等于没验。这里验的是平台这一半 —— 决策被正确重排、原样交到智能体手里、
run 从 `waiting_approval` 回到队列并跑到终态。
"""

from functools import partial
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api.platform import Platform
from event.model import EventType, InterruptAction, RunStatus
from run.approval import DEFAULT_PENDING_LIMIT
from run.decision import DecisionType
from test.api.conftest import Agent, drain

# 教师会看到的那次待确认调用
PENDING = [InterruptAction(index=0, tool_name="delete", args={"file_path": "/workspace/data.csv"})]

FOUR_DECISIONS = (
    {"index": 0, "type": DecisionType.APPROVE.value},
    {"index": 0, "type": DecisionType.REJECT.value, "message": "这段代码会删掉原始数据"},
    {
        "index": 0,
        "type": DecisionType.EDIT.value,
        "edited_action": {"name": "delete", "args": {"file_path": "/workspace/outputs/tmp.csv"}},
    },
    {"index": 0, "type": DecisionType.RESPOND.value, "message": "直接用去年的口径即可"},
)


def _interrupted(client: TestClient, agent: Agent, thread_id: str) -> str:
    """提交一次分析，让它停在等人确认上。"""
    agent.interrupt = list(PENDING)
    run_id: str = client.post(f"/api/threads/{thread_id}/runs", json={"content": "删掉旧数据"}).json()["id"]
    _settle(client, run_id, RunStatus.WAITING_APPROVAL)
    return run_id


def _settle(client: TestClient, run_id: str, expected: RunStatus) -> None:
    """等 worker 把状态推到目标态。同进程里的 worker 很快，但不是同步的。"""
    for _ in range(200):
        if client.get(f"/api/runs/{run_id}").json()["status"] == expected.value:
            return
        client.get("/api/auth/me")
    raise AssertionError(f"run 没能走到 {expected.value}")


@pytest.mark.parametrize("decision", FOUR_DECISIONS)
def test_each_of_the_four_decisions_lets_the_run_finish(
    client: TestClient, agent: Agent, thread_id: str, decision: dict[str, object]
) -> None:
    run_id = _interrupted(client, agent, thread_id)

    response = client.post(f"/api/runs/{run_id}/approve", json={"decisions": [decision]})

    assert response.status_code == 202
    _settle(client, run_id, RunStatus.SUCCEEDED)


def test_the_decision_reaches_the_agent_in_the_shape_it_expects(
    client: TestClient, agent: Agent, thread_id: str
) -> None:
    run_id = _interrupted(client, agent, thread_id)

    client.post(
        f"/api/runs/{run_id}/approve",
        json={"decisions": [{"index": 0, "type": "reject", "message": "不行"}]},
    )
    _settle(client, run_id, RunStatus.SUCCEEDED)

    assert agent.resumed == [[{"type": "reject", "message": "不行"}]]


def test_the_interrupt_event_reaches_the_teacher(client: TestClient, agent: Agent, thread_id: str) -> None:
    run_id = _interrupted(client, agent, thread_id)
    client.post(f"/api/runs/{run_id}/approve", json={"decisions": [{"index": 0, "type": "approve"}]})

    line = drain(client, run_id)

    assert f"event: {EventType.INTERRUPT.value}" in line


def test_the_resumed_run_says_it_is_a_resume(client: TestClient, agent: Agent, thread_id: str) -> None:
    """一次 run 会多次入队 —— `run.started` 因此有两条，但只有一条是「第一次开跑」。"""
    run_id = _interrupted(client, agent, thread_id)
    client.post(f"/api/runs/{run_id}/approve", json={"decisions": [{"index": 0, "type": "approve"}]})

    line = drain(client, run_id)

    started = [one for one in line if one.startswith("data:") and '"run.started"' in one]
    assert len(started) == 2
    assert len([one for one in started if '"resumed":false' in one.replace(" ", "")]) == 1


def test_a_missing_index_is_a_validation_error(client: TestClient, agent: Agent, thread_id: str) -> None:
    """两个待确认的调用只回一个决策 —— 恢复时会把 A 的决策套到 B 的调用上。"""
    agent.interrupt = [
        InterruptAction(index=0, tool_name="delete", args={"file_path": "/workspace/a.csv"}),
        InterruptAction(index=1, tool_name="delete", args={"file_path": "/workspace/b.csv"}),
    ]
    run_id = client.post(f"/api/threads/{thread_id}/runs", json={"content": "删两个"}).json()["id"]
    _settle(client, run_id, RunStatus.WAITING_APPROVAL)

    response = client.post(f"/api/runs/{run_id}/approve", json={"decisions": [{"index": 0, "type": "approve"}]})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_a_duplicated_index_is_a_validation_error(client: TestClient, agent: Agent, thread_id: str) -> None:
    run_id = _interrupted(client, agent, thread_id)

    response = client.post(
        f"/api/runs/{run_id}/approve",
        json={"decisions": [{"index": 0, "type": "approve"}, {"index": 0, "type": "approve"}]},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_a_run_that_is_not_waiting_cannot_be_approved(client: TestClient, agent: Agent, thread_id: str) -> None:
    agent.blocked = False
    run_id = client.post(f"/api/threads/{thread_id}/runs", json={"content": "一"}).json()["id"]
    drain(client, run_id)

    response = client.post(f"/api/runs/{run_id}/approve", json={"decisions": [{"index": 0, "type": "approve"}]})

    assert response.status_code == 422


def test_another_users_run_cannot_be_approved(client: TestClient, agent: Agent, thread_id: str) -> None:
    run_id = _interrupted(client, agent, thread_id)
    client.cookies.clear()

    response = client.post(f"/api/runs/{run_id}/approve", json={"decisions": [{"index": 0, "type": "approve"}]})

    assert response.status_code == 401


def test_a_waiting_run_does_not_occupy_a_concurrency_slot(
    client: TestClient, agent: Agent, platform: Platform, thread_id: str
) -> None:
    """并发配额限制的是资源占用，而等人确认既不占 worker 也不占沙箱。

    算进来的话，教师忘了点确认就会把自己的配额锁死一整天。
    """
    _interrupted(client, agent, thread_id)
    assert client.portal is not None
    identity = client.get("/api/auth/me").json()["id"]

    assert client.portal.call(partial(platform.usage.active_run, identity)) == 0


def test_too_many_waiting_approvals_block_a_new_submission(client: TestClient, agent: Agent, thread_id: str) -> None:
    """不占资源不等于可以无限堆积。这是防堆积的那道闸，与资源无关。"""
    for _ in range(DEFAULT_PENDING_LIMIT):
        _interrupted(client, agent, thread_id)

    response = client.post(f"/api/threads/{thread_id}/runs", json={"content": "再来一个"})

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "CONCURRENCY_LIMIT"


def test_an_unknown_run_cannot_be_approved(client: TestClient) -> None:
    response = client.post(f"/api/runs/{uuid4().hex}/approve", json={"decisions": [{"index": 0, "type": "approve"}]})

    assert response.status_code == 404
