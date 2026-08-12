"""broker 的抓取端点：沙箱容器数与内存。

内存的读法是注入的假货，不去问真 docker —— 否则这条用例在没装 docker 的机器上会
「通过」，而它本该验的东西一个字都没验到。
"""

from http import HTTPStatus
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from prometheus_client.parser import text_string_to_metric_families

from broker.app import create_app
from broker.runtime import Broker
from sandbox.workspace import Workspace

BROKER_URL = "http://broker.test"
METRIC_PATH = "/metrics"

USED_BYTE = 5 << 30
CONTAINER_COUNT = 2


class FakePool:
    @property
    def size(self) -> int:
        return CONTAINER_COUNT


@pytest.fixture
def app(tmp_path: Path) -> FastAPI:
    return create_app(
        Broker(workspace=Workspace(root=tmp_path), pool=FakePool(), memory=lambda: USED_BYTE)  # type: ignore[arg-type]
    )


@pytest.fixture
def client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BROKER_URL)


def sampled(text: str) -> dict[str, float]:
    """把响应正文解析回「指标名 → 值」。

    不直接在正文里找字符串：`5368709120` 在 Prometheus 的文本格式里印成
    `5.36870912e+09`，断字符串等于在断浮点的打印格式。
    """
    return {sample.name: sample.value for family in text_string_to_metric_families(text) for sample in family.samples}


async def test_the_scrape_endpoint_reports_sandbox_occupancy(client: httpx.AsyncClient) -> None:
    """**只有 broker 数得出这两个数** —— 它是唯一持有 docker.sock 的进程。"""
    async with client:
        response = await client.get(METRIC_PATH)

    assert response.status_code == 200
    assert sampled(response.text)["zuel_sandbox_container"] == CONTAINER_COUNT
    assert sampled(response.text)["zuel_sandbox_memory_byte"] == USED_BYTE


async def test_the_scrape_endpoint_is_not_under_the_threads_prefix(client: httpx.AsyncClient) -> None:
    """它不是 api 够得着的那组能力里的一个，调用方是 Prometheus。

    **判据是「那里取不到指标」，不是某个具体状态码。** `/threads/{thread_id}` 这类
    单段路由一旦存在，这条路径就会因为方法不匹配而答 405 而不是 404 —— 而 405 与 404
    在这里说的是同一件事：指标不在这儿。钉死状态码只会让加一条会话端点就红一次。
    """
    async with client:
        response = await client.get("/threads/metrics")

    assert response.status_code != HTTPStatus.OK
    assert "zuel_sandbox_container" not in response.text
