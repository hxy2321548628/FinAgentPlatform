import json

from fastapi.testclient import TestClient

from sandbox.path import OUTPUT_DIR
from sandbox.workspace import Workspace
from test.api.conftest import Agent, drain

PNG = b"\x89PNG\r\n\x1a\n"


def make_artifact(space: Workspace, thread_id: str, name: str, content: bytes = PNG) -> None:
    target = space.path(thread_id) / OUTPUT_DIR / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)


def test_an_artifact_is_returned_as_bytes(client: TestClient, thread_id: str, space: Workspace) -> None:
    """本期没有对象存储可跳，网关直接回字节。"""
    make_artifact(space, thread_id, "chart.png")

    response = client.get(f"/api/artifacts/{thread_id}/chart.png")

    assert response.status_code == 200
    assert response.content == PNG


def test_the_content_type_lets_a_browser_display_it(client: TestClient, thread_id: str, space: Workspace) -> None:
    make_artifact(space, thread_id, "chart.png")

    response = client.get(f"/api/artifacts/{thread_id}/chart.png")

    assert response.headers["content-type"] == "image/png"


def test_a_nested_artifact_is_reachable(client: TestClient, thread_id: str, space: Workspace) -> None:
    make_artifact(space, thread_id, "figure/chart.png")

    assert client.get(f"/api/artifacts/{thread_id}/figure/chart.png").status_code == 200


def test_a_missing_artifact_is_not_found(client: TestClient, thread_id: str) -> None:
    response = client.get(f"/api/artifacts/{thread_id}/never-made.png")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_an_artifact_of_an_unknown_thread_is_not_found(client: TestClient) -> None:
    assert client.get("/api/artifacts/never-created/chart.png").status_code == 404


def test_an_id_without_a_path_is_not_found(client: TestClient, thread_id: str) -> None:
    assert client.get(f"/api/artifacts/{thread_id}").status_code == 404


def test_a_file_outside_the_output_directory_is_not_reachable(
    client: TestClient, thread_id: str, space: Workspace
) -> None:
    """不挡住的话，产物下载就成了任意文件读取。"""
    (space.path(thread_id) / "holdings.csv").write_bytes(b"a,b\n")

    response = client.get(f"/api/artifacts/{thread_id}/../holdings.csv")

    assert response.status_code == 404


def test_the_run_reports_ids_that_the_artifact_endpoint_accepts(
    client: TestClient, thread_id: str, agent: Agent
) -> None:
    """run.finished 给的标识拼上端点就该能下载 —— 否则教师只能从答复文本里猜路径。"""
    agent.produce = {"industry_volatility.png": PNG}
    run_id = client.post(f"/api/threads/{thread_id}/runs", json={"content": "画个图"}).json()["id"]

    line = drain(client, run_id)
    finished = json.loads(next(one for one in line if '"run.finished"' in one).partition(": ")[2])
    artifacts = finished["data"]["artifacts"]

    assert artifacts == [f"{thread_id}/industry_volatility.png"]
    assert client.get(f"/api/artifacts/{artifacts[0]}").content == PNG


def test_an_encoded_traversal_is_rejected(client: TestClient, thread_id: str, space: Workspace) -> None:
    """裸 HTTP 请求可以带未规范化的 `..`，客户端库替我们消掉的那一层不能当成防线。"""
    (space.path(thread_id) / "holdings.csv").write_bytes(b"a,b\n")

    response = client.get(f"/api/artifacts/{thread_id}/%2E%2E%2Fholdings.csv")

    assert response.status_code == 404
