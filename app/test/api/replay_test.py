"""一次性取回一个 run 的全部过程。

**为什么不复用事件流那条端点**：SSE 每次重连都要过一次频率闸，而翻旧账的
那些 run 早就不会再产生事件了 —— 拿一条长连接去读一份不再变化的历史，
连接断了还要重连，重连又消耗名额。已经结束的 run 走这条一次性端点，
读完即止，可缓存，断了就是断了。

正在跑的那一条仍旧走 SSE：它要的是「新事件一产生就推过来」。
"""

from functools import partial
from uuid import uuid4

from fastapi.testclient import TestClient
from redis.asyncio import Redis

from run.log import stream_key
from test.api.conftest import Agent, drain
from test.api.run_test import submit, token


def replay(client: TestClient, run_id: str) -> list[dict[str, object]]:
    body = client.get(f"/api/runs/{run_id}/replay")
    assert body.status_code == 200
    items: list[dict[str, object]] = body.json()["items"]
    return items


def _event(item: dict[str, object]) -> dict[str, object]:
    """取出一条回放里的事件本身。"""
    event = item["event"]
    assert isinstance(event, dict)
    return event


def _payload(event: dict[str, object]) -> dict[str, object]:
    """取出一个事件的载荷。"""
    data = event["data"]
    assert isinstance(data, dict)
    return data


def test_the_replay_spells_out_the_whole_run(client: TestClient, thread_id: str, agent: Agent) -> None:
    """与事件流吐出来的是同一份历史，只是一次给完。"""
    agent.chunk = [token("好"), token("的")]
    run_id = submit(client, thread_id)
    drain(client, run_id)

    spelled = [_event(one)["type"] for one in replay(client, run_id)]

    assert spelled == ["run.started", "sandbox.ready", "token", "run.finished"]


def test_adjacent_increments_arrive_already_merged(client: TestClient, thread_id: str, agent: Agent) -> None:
    """两个 token 增量在流里是两条，在这里是一条 —— 一轮实测上万条，逐条给既慢又白费。"""
    agent.chunk = [token("波动"), token("率")]
    run_id = submit(client, thread_id)
    drain(client, run_id)

    spoken = [_event(one) for one in replay(client, run_id) if _event(one)["type"] == "token"]

    assert len(spoken) == 1
    assert _payload(spoken[0])["text"] == "波动率"


def test_every_item_carries_its_position(client: TestClient, thread_id: str, agent: Agent) -> None:
    """每条都带着它在日志里的位置，前端拿它接着订阅还没发生的那部分。"""
    agent.chunk = [token("好")]
    run_id = submit(client, thread_id)
    drain(client, run_id)

    assert all(one["id"] for one in replay(client, run_id))


def test_the_event_shape_is_the_same_contract_as_the_stream(client: TestClient, thread_id: str, agent: Agent) -> None:
    """前端只有一套事件校验 —— 两条端点给的形状不一样就得写两套。"""
    agent.chunk = [token("好的")]
    run_id = submit(client, thread_id)
    drain(client, run_id)

    spoken = next(_event(one) for one in replay(client, run_id) if _event(one)["type"] == "token")

    assert set(spoken) == {"type", "ts", "run_id", "path", "data"}
    assert _payload(spoken) == {"text": "好的"}


def test_replaying_an_unknown_run_is_not_found(client: TestClient) -> None:
    assert client.get(f"/api/runs/{uuid4().hex}/replay").status_code == 404


def test_a_run_whose_events_expired_replays_empty_instead_of_failing(
    client: TestClient, thread_id: str, agent: Agent, live_cache: Redis
) -> None:
    """事件留 180 天而 `runs` 那一行不清 —— 过期之后这里该是空列表，不是报错。"""
    agent.chunk = [token("很久以前")]
    run_id = submit(client, thread_id)
    drain(client, run_id)
    assert client.portal is not None
    client.portal.call(partial(live_cache.delete, stream_key(run_id)))

    assert replay(client, run_id) == []
