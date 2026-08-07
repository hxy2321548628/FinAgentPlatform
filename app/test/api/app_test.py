"""应用组装本身的测试。"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from api.app import create_app
from api.platform import build_platform
from config import Settings
from sandbox.remote import RemoteSandboxPool, RemoteWorkspace
from store.postgres import PostgresUnavailableError
from store.redis import RedisUnavailableError

# 不会有人监听的端口，连不上是立刻的 ECONNREFUSED
DEAD_PORT = 1


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


@pytest.mark.usefixtures("no_proxy", "live_engine", "live_cache")
async def test_a_platform_built_from_settings_wires_everything_together(tmp_path: Path) -> None:
    settings = Settings(deepseek_api_key=SecretStr("sk-test"), sandbox_workspace_root=tmp_path)

    platform = await build_platform(settings)

    try:
        # 装配阶段不该碰 broker、不该碰盘：这三样都只是拿到了一条到 broker 的连接
        assert isinstance(platform.workspace, RemoteWorkspace)
        assert isinstance(platform.pool, RemoteSandboxPool)
        assert await platform.executor.get("never-existed") is None
    finally:
        await platform.engine.dispose()
        await platform.cache.aclose()


@pytest.mark.usefixtures("no_proxy")
async def test_building_a_platform_fails_when_postgres_is_unreachable(tmp_path: Path) -> None:
    """步骤零的验证标准②：连不上要在装配那一刻炸，不是撑到第一次落库。

    「能启动但一查就 500」的进程，会让之后每一次故障都多一个候选原因。
    """
    settings = Settings(
        deepseek_api_key=SecretStr("sk-test"),
        sandbox_workspace_root=tmp_path,
        postgres_port=DEAD_PORT,
    )

    with pytest.raises(PostgresUnavailableError):
        await build_platform(settings)


@pytest.mark.usefixtures("no_proxy", "live_engine", "live_cache")
async def test_building_a_platform_fails_when_redis_is_unreachable(tmp_path: Path) -> None:
    settings = Settings(
        deepseek_api_key=SecretStr("sk-test"),
        sandbox_workspace_root=tmp_path,
        redis_url=f"redis://127.0.0.1:{DEAD_PORT}/0",
    )

    with pytest.raises(RedisUnavailableError):
        await build_platform(settings)


@pytest.mark.usefixtures("no_proxy", "live_engine", "live_cache")
def test_an_app_without_an_injected_platform_builds_its_own(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """生产走的是这条路径：uvicorn 起进程时没有人给它塞运行时。

    只验它能自己起得来、并把运行时挂上去。**不在这里发业务请求** —— 拆出 broker
    之后那需要一个真的 broker 在跑，那是 deploy/test/ 里的集成验收，不是单测。
    """
    settings = Settings(deepseek_api_key=SecretStr("sk-test"), sandbox_workspace_root=tmp_path)
    monkeypatch.setattr("api.app.get_settings", lambda: settings)

    with TestClient(create_app()) as client:
        assert client.app.state.platform.executor is not None  # type: ignore[attr-defined]
        assert client.get("/docs").status_code == 200
