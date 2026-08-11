from fastapi.testclient import TestClient

from event.model import RunStatus
from sandbox.workspace import Workspace
from test.api.conftest import Agent, drain

# 工作目录里的文件（上传、列结构、预览、下载、删除）全部在 file_test.py


# ------------------------------------------------------------------ 建会话
def test_creating_a_thread_returns_its_id(client: TestClient) -> None:
    response = client.post("/api/threads")

    assert response.status_code == 201
    assert response.json()["id"]


def test_each_thread_gets_a_distinct_id(client: TestClient) -> None:
    first = client.post("/api/threads").json()["id"]
    second = client.post("/api/threads").json()["id"]

    assert first != second


def test_a_created_thread_has_a_workspace(client: TestClient, space: Workspace) -> None:
    thread_id = client.post("/api/threads").json()["id"]

    assert space.exists(thread_id)


# ------------------------------------------------------------------ 提交分析
def test_submitting_a_run_returns_202_immediately(client: TestClient, thread_id: str) -> None:
    """任务要跑几十分钟，提交不能等它完成。"""
    response = client.post(f"/api/threads/{thread_id}/runs", json={"content": "算个波动率"})

    assert response.status_code == 202
    assert response.json()["thread_id"] == thread_id
    assert response.json()["status"] == RunStatus.QUEUED.value


def test_the_question_reaches_the_agent(client: TestClient, thread_id: str, agent: Agent) -> None:
    run_id = client.post(f"/api/threads/{thread_id}/runs", json={"content": "按行业分组算年化波动率"}).json()["id"]
    drain(client, run_id)

    assert agent.asked == ["按行业分组算年化波动率"]


def test_submitting_to_an_unknown_thread_is_not_found(client: TestClient) -> None:
    response = client.post("/api/threads/never-created/runs", json={"content": "一"})

    assert response.status_code == 404


def test_an_empty_question_is_rejected(client: TestClient, thread_id: str) -> None:
    response = client.post(f"/api/threads/{thread_id}/runs", json={"content": ""})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_a_missing_body_is_rejected(client: TestClient, thread_id: str) -> None:
    response = client.post(f"/api/threads/{thread_id}/runs")

    assert response.status_code == 422


def test_a_thread_id_that_escapes_the_root_is_not_found(client: TestClient) -> None:
    """会话标识参与拼路径，非法值的回答该是 404 而不是 500。"""
    response = client.post("/api/threads/..%2F..%2Fetc/runs", json={"content": "一"})

    assert response.status_code == 404
