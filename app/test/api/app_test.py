"""应用组装本身的测试。"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from api.app import create_app
from api.platform import build_platform
from config import Settings


@pytest.fixture
def no_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    """开发机的 socks 代理会让 ChatDeepSeek 构造直接报错，与被测行为无关。"""
    for name in ("ALL_PROXY", "all_proxy"):
        monkeypatch.delenv(name, raising=False)


def test_an_unknown_route_uses_the_platform_error_shape(client: TestClient) -> None:
    """框架自己抛的 404 也得是这个形状，否则前端要同时认两种错误。"""
    response = client.get("/api/nothing-here")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_the_openapi_document_is_served(client: TestClient) -> None:
    """字段级的接口文档以它为准，不手写第二份。"""
    paths = client.get("/openapi.json").json()["paths"]

    assert set(paths) == {
        "/api/threads",
        "/api/threads/{thread_id}/files",
        "/api/threads/{thread_id}/runs",
        "/api/runs/{run_id}",
        "/api/runs/{run_id}/events",
        "/api/artifacts/{artifact_id}",
    }


@pytest.mark.usefixtures("no_proxy")
def test_a_platform_built_from_settings_wires_everything_together(tmp_path: Path) -> None:
    settings = Settings(deepseek_api_key=SecretStr("sk-test"), sandbox_workspace_root=tmp_path)

    platform = build_platform(settings)

    assert platform.workspace.create()
    assert platform.pool.size == 0
    assert platform.executor.get("never-existed") is None


@pytest.mark.usefixtures("no_proxy")
def test_an_app_without_an_injected_platform_builds_its_own(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """生产走的是这条路径：uvicorn 起进程时没有人给它塞运行时。"""
    settings = Settings(deepseek_api_key=SecretStr("sk-test"), sandbox_workspace_root=tmp_path)
    monkeypatch.setattr("api.app.get_settings", lambda: settings)

    with TestClient(create_app()) as client:
        assert client.post("/api/threads").status_code == 201
