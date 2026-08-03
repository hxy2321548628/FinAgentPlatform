import json

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessageChunk

from event.mapper import StreamChunk
from event.model import RunStatus
from test.api.conftest import Agent, drain


def token(text: str) -> StreamChunk:
    return ((), "messages", (AIMessageChunk(content=text), {}))


def submit(client: TestClient, thread_id: str, content: str = "算个波动率") -> str:
    run_id: str = client.post(f"/api/threads/{thread_id}/runs", json={"content": content}).json()["id"]
    return run_id


def parse(line: list[str]) -> list[dict[str, str]]:
    """把 SSE 的行还原成 {id, event, data} 三元组。"""
    frame: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for one in line:
        field, _, value = one.partition(": ")
        current[field] = value
        if field == "data":
            frame.append(current)
            current = {}
    return frame


# ------------------------------------------------------------------ 查状态
def test_a_finished_run_reports_succeeded(client: TestClient, thread_id: str, agent: Agent) -> None:
    agent.chunk = [token("好的")]
    run_id = submit(client, thread_id)
    drain(client, run_id)

    response = client.get(f"/api/runs/{run_id}")

    assert response.status_code == 200
    assert response.json() == {"id": run_id, "thread_id": thread_id, "status": RunStatus.SUCCEEDED.value}


def test_a_failed_run_reports_failed(client: TestClient, thread_id: str, agent: Agent) -> None:
    agent.side_effect = RuntimeError("模型连接断了")
    run_id = submit(client, thread_id)
    drain(client, run_id)

    assert client.get(f"/api/runs/{run_id}").json()["status"] == RunStatus.FAILED.value


def test_an_unknown_run_is_not_found(client: TestClient) -> None:
    response = client.get("/api/runs/never-existed")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


# ------------------------------------------------------------------ SSE 形状
def test_the_stream_is_served_as_server_sent_events(client: TestClient, thread_id: str) -> None:
    run_id = submit(client, thread_id)

    with client.stream("GET", f"/api/runs/{run_id}/events") as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.headers["cache-control"] == "no-cache"
        list(response.iter_lines())


def test_every_frame_carries_an_id_for_reconnecting(client: TestClient, thread_id: str, agent: Agent) -> None:
    """没有 id 行，浏览器重连时就无从告诉服务端自己读到哪了。"""
    agent.chunk = [token("好"), token("的")]
    run_id = submit(client, thread_id)

    frame = parse(drain(client, run_id))

    assert all(one["id"] for one in frame)
    assert all(one["event"] for one in frame)


def test_the_frames_spell_out_the_whole_run(client: TestClient, thread_id: str, agent: Agent) -> None:
    agent.chunk = [token("好"), token("的")]
    run_id = submit(client, thread_id)

    frame = parse(drain(client, run_id))

    assert [one["event"] for one in frame] == [
        "run.started",
        "sandbox.ready",
        "token",
        "token",
        "run.finished",
    ]


def test_the_data_line_is_the_event_contract(client: TestClient, thread_id: str, agent: Agent) -> None:
    """前端的校验 schema 照事件模型写，这一行必须就是那个形状。"""
    agent.chunk = [token("好的")]
    run_id = submit(client, thread_id)

    frame = parse(drain(client, run_id))
    payload = json.loads(next(one["data"] for one in frame if one["event"] == "token"))

    assert payload == {
        "type": "token",
        "ts": payload["ts"],
        "run_id": run_id,
        "path": [],
        "data": {"text": "好的"},
    }


def test_the_stream_closes_when_the_run_ends(client: TestClient, thread_id: str, agent: Agent) -> None:
    """不收尾的话，教师那一侧就是一个永远转圈的连接。"""
    agent.chunk = [token("好")]
    run_id = submit(client, thread_id)

    frame = parse(drain(client, run_id))

    assert frame[-1]["event"] == "run.finished"


def test_a_failing_run_still_closes_the_stream(client: TestClient, thread_id: str, agent: Agent) -> None:
    agent.side_effect = RuntimeError("模型连接断了")
    run_id = submit(client, thread_id)

    frame = parse(drain(client, run_id))

    assert frame[-1]["event"] == "run.failed"
    assert json.loads(frame[-1]["data"])["data"]["retryable"] is False


def test_streaming_an_unknown_run_is_not_found(client: TestClient) -> None:
    response = client.get("/api/runs/never-existed/events")

    assert response.status_code == 404


# ------------------------------------------------------------------ 断线重连
def test_reconnecting_replays_exactly_what_was_missed(client: TestClient, thread_id: str, agent: Agent) -> None:
    """断线重连的核心保证：补齐的部分与已收到的部分严丝合缝。"""
    agent.chunk = [token(str(index)) for index in range(10)]
    run_id = submit(client, thread_id)
    whole = parse(drain(client, run_id))

    for cut in range(len(whole)):
        received = whole[: cut + 1]
        replayed = parse(
            drain_with_cursor(client, run_id, received[-1]["id"]),
        )

        assert [one["id"] for one in received + replayed] == [one["id"] for one in whole]


def drain_with_cursor(client: TestClient, run_id: str, last_event_id: str) -> list[str]:
    with client.stream(
        "GET",
        f"/api/runs/{run_id}/events",
        headers={"Last-Event-ID": last_event_id},
    ) as response:
        return [line for line in response.iter_lines() if line]


def test_reconnecting_at_the_last_event_replays_nothing(client: TestClient, thread_id: str, agent: Agent) -> None:
    agent.chunk = [token("好")]
    run_id = submit(client, thread_id)
    whole = parse(drain(client, run_id))

    assert drain_with_cursor(client, run_id, whole[-1]["id"]) == []


def test_reconnecting_without_the_header_replays_everything(client: TestClient, thread_id: str, agent: Agent) -> None:
    """首次连接不带这个头，此时该拿到完整历史而不是空流。"""
    agent.chunk = [token("好")]
    run_id = submit(client, thread_id)
    whole = parse(drain(client, run_id))

    assert parse(drain(client, run_id)) == whole


def test_an_empty_cursor_reads_as_a_first_connection(client: TestClient, thread_id: str, agent: Agent) -> None:
    """浏览器不会发空值，但中间的代理有时会补一个。"""
    agent.chunk = [token("好")]
    run_id = submit(client, thread_id)
    whole = parse(drain(client, run_id))

    assert parse(drain_with_cursor(client, run_id, "")) == whole


def test_a_malformed_cursor_is_rejected(client: TestClient, thread_id: str) -> None:
    """游标来自请求头，是不可信输入 —— 认不出来要说清楚，不能当成从头开始。"""
    run_id = submit(client, thread_id)

    response = client.get(f"/api/runs/{run_id}/events", headers={"Last-Event-ID": "not-an-id"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_two_subscribers_of_one_run_see_the_same_stream(client: TestClient, thread_id: str, agent: Agent) -> None:
    """教师可能开着两个标签页。"""
    agent.chunk = [token("好")]
    run_id = submit(client, thread_id)

    first = parse(drain(client, run_id))
    second = parse(drain(client, run_id))

    assert first == second
