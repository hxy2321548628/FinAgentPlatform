import io

from fastapi.testclient import TestClient

from event.model import RunStatus
from sandbox.workspace import Workspace
from test.api.conftest import Agent, drain


def upload(client: TestClient, thread_id: str, filename: str, content: bytes = b"a,b\n") -> object:
    return client.post(f"/api/threads/{thread_id}/files", files={"file": (filename, io.BytesIO(content), "text/csv")})


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


# ------------------------------------------------------------------ 上传
def test_uploading_a_file_lands_it_in_the_workspace(client: TestClient, thread_id: str, space: Workspace) -> None:
    response = upload(client, thread_id, "holdings.csv")

    assert response.status_code == 201  # type: ignore[attr-defined]
    assert (space.path(thread_id) / "holdings.csv").read_bytes() == b"a,b\n"


def test_the_upload_response_reports_what_landed(client: TestClient, thread_id: str) -> None:
    response = upload(client, thread_id, "holdings.csv", b"a,b\nc,d\n")

    assert response.json() == {"filename": "holdings.csv", "size": 8}  # type: ignore[attr-defined]


def test_uploading_to_an_unknown_thread_is_not_found(client: TestClient) -> None:
    response = upload(client, "never-created", "holdings.csv")

    assert response.status_code == 404  # type: ignore[attr-defined]
    assert response.json()["error"]["code"] == "NOT_FOUND"  # type: ignore[attr-defined]


def test_a_traversing_filename_cannot_escape_the_workspace(
    client: TestClient, thread_id: str, space: Workspace
) -> None:
    """文件名来自 HTTP 请求，是不可信输入。"""
    upload(client, thread_id, "../../escaped.csv")

    assert not (space.path(thread_id).parent.parent / "escaped.csv").exists()


def test_uploading_without_a_file_is_a_validation_error(client: TestClient, thread_id: str) -> None:
    response = client.post(f"/api/threads/{thread_id}/files")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


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


def test_a_filename_with_no_usable_segment_is_rejected(client: TestClient, thread_id: str) -> None:
    """`..` 收成末段之后什么都不剩，落不了盘。"""
    response = upload(client, thread_id, "..")

    assert response.status_code == 404  # type: ignore[attr-defined]
    assert response.json()["error"]["code"] == "NOT_FOUND"  # type: ignore[attr-defined]
