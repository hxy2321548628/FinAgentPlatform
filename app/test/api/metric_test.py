"""抓取端点：给得出 Prometheus 认得的文本，且不要求登录。

**「不要求登录」是这里最该被写死的一条**，两个方向都要盯：漏挂鉴权与多挂鉴权都会坏事。
多挂了 Prometheus 就抓不到（而它只会在 `up` 上显示为 0，没人盯着就等于没有监控）；
而响应里带着用户名与他今天的 token，因此挡它的责任全在 nginx 那一条 `return 404` 上。
"""

from fastapi.testclient import TestClient

from test.api.conftest import Agent, drain

METRIC_PATH = "/metrics"


def test_the_scrape_endpoint_needs_no_session(client: TestClient) -> None:
    """Prometheus 没有会话。给它发一份长期凭据只是把同一个问题换个地方放。"""
    client.cookies.clear()

    response = client.get(METRIC_PATH)

    assert response.status_code == 200


def test_the_scrape_endpoint_speaks_the_prometheus_text_format(client: TestClient) -> None:
    """内容类型错了 Prometheus 会静默丢掉整次抓取。"""
    response = client.get(METRIC_PATH)

    assert response.headers["content-type"].startswith("text/plain")
    assert "# HELP zuel_run " in response.text


def test_a_run_shows_up_in_the_scrape(client: TestClient, thread_id: str, agent: Agent) -> None:
    """端点与指标之间的接线要真的通。

    **不断言具体数值**：那是 test/metric/platform_test.py 的事，这里只验「路由取到的
    是同一份运行时」—— 接错了 Platform 字段时数字会是 0 而不是报错。
    """
    agent.chunk = []
    run_id = client.post(f"/api/threads/{thread_id}/runs", json={"content": "问题"}).json()["id"]
    drain(client, run_id)

    text = client.get(METRIC_PATH).text

    assert 'zuel_run{status="queued"}' in text
    assert "zuel_task_pending " in text
    assert "zuel_token_today" in text


def test_the_scrape_endpoint_is_outside_the_api_prefix(client: TestClient) -> None:
    """带上 /api 前缀的话它会被那一层的登录与限流拦住。"""
    assert client.get("/api/metrics").status_code == 404
