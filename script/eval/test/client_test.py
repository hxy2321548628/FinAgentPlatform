"""平台客户端的测试。

**批准那一段值得单测**：一次中断可能停下不止一个调用，少批一个是 422，
而那个红看着像 agent 没做好 —— 首轮就是这么白跑了一道题。
"""

import httpx
import pytest
from client import RESPOND_MESSAGE, PlatformClient


def a_client(handler: object) -> PlatformClient:
    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    return PlatformClient(
        base_url="http://platform", client=httpx.Client(transport=transport)
    )


def test_approval_covers_every_pending_action() -> None:
    """两个待确认调用就要回两个决策，index 照抄平台给的。"""
    sent: list[dict[str, object]] = []
    state = {"status": "waiting_approval"}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/replay"):
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "1-0",
                            "event": {
                                "type": "interrupt",
                                "data": {
                                    "actions": [
                                        {
                                            "index": 0,
                                            "tool_name": "delete",
                                            "allowed_decisions": ["approve", "reject"],
                                        },
                                        {
                                            "index": 1,
                                            "tool_name": "delete",
                                            "allowed_decisions": ["approve"],
                                        },
                                    ]
                                },
                            },
                        }
                    ]
                },
            )
        if request.url.path.endswith("/approve"):
            import json

            sent.append(json.loads(request.content))
            state["status"] = "succeeded"
            return httpx.Response(202, json={})
        return httpx.Response(200, json={"status": state["status"]})

    status, approvals = a_client(handler).wait("run-1")

    assert status == "succeeded"
    assert approvals == 1
    assert sent == [
        {
            "decisions": [
                {"index": 0, "type": "approve"},
                {"index": 1, "type": "approve"},
            ]
        }
    ]


def test_a_tool_that_forbids_approval_gets_what_it_allows() -> None:
    """只允许别的决策时按它允许的来，硬发 approve 同样是 422。"""
    sent: list[dict[str, object]] = []
    state = {"status": "waiting_approval"}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/replay"):
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "1-0",
                            "event": {
                                "type": "interrupt",
                                "data": {
                                    "actions": [
                                        {"index": 0, "allowed_decisions": ["reject"]}
                                    ]
                                },
                            },
                        }
                    ]
                },
            )
        if request.url.path.endswith("/approve"):
            import json

            sent.append(json.loads(request.content))
            state["status"] = "cancelled"
            return httpx.Response(202, json={})
        return httpx.Response(200, json={"status": state["status"]})

    a_client(handler).wait("run-1")

    assert sent == [{"decisions": [{"index": 0, "type": "reject"}]}]


def test_no_approval_is_sent_before_the_interrupt_event_lands() -> None:
    """事件还没落进日志时先不批 —— 拿空列表硬发一次必然 422。"""
    calls = {"approve": 0, "poll": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/replay"):
            return httpx.Response(200, json={"items": []})
        if request.url.path.endswith("/approve"):
            calls["approve"] += 1
            return httpx.Response(202, json={})
        calls["poll"] += 1
        # 第二轮轮询就结束，免得测试真的等下去
        return httpx.Response(
            200,
            json={"status": "waiting_approval" if calls["poll"] < 2 else "succeeded"},
        )

    status, approvals = a_client(handler).wait("run-1")

    assert status == "succeeded"
    assert calls["approve"] == 0
    assert approvals == 0


DEFAULT_POLL = 5


def test_the_poll_interval_can_be_widened_for_concurrent_runs() -> None:
    """并发跑时必须放慢轮询，否则打的是自己账号的限流。

    **算一遍就知道躲不过**：限流 120 次/分钟、按用户计，而每个等待中的 run
    每 `poll_second` 秒查一次状态 —— 5 秒 × 10 个并发正好 120 次/分钟，
    加上提交与取结果必然超。**超了报的是 RATE_LIMITED**，看着像平台出问题，
    实际是跑批自己把自己打下来的。
    """
    with httpx.Client() as raw:
        assert (
            PlatformClient(base_url="http://x", client=raw).poll_second == DEFAULT_POLL
        )
        assert (
            PlatformClient(base_url="http://x", client=raw, poll_second=20).poll_second
            == 20
        )


def test_a_question_gets_an_answer_not_a_bare_respond() -> None:
    """`ask_user_question` 只允许 `respond`，而不带话的 `respond` 平台会挡回来。

    挡不住的话它炸在恢复那一刻、run 记成 `INTERNAL` —— 跑批看到的是一道题
    莫名其妙地失败，而错误信息一个字都不指向「少了一句话」。
    """
    sent: list[dict[str, object]] = []
    state = {"status": "waiting_approval"}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/replay"):
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "1-0",
                            "event": {
                                "type": "interrupt",
                                "data": {
                                    "actions": [
                                        {
                                            "index": 0,
                                            "tool_name": "ask_user_question",
                                            "allowed_decisions": ["respond"],
                                        }
                                    ]
                                },
                            },
                        }
                    ]
                },
            )
        if request.url.path.endswith("/approve"):
            import json

            sent.append(json.loads(request.content))
            state["status"] = "succeeded"
            return httpx.Response(202, json={})
        return httpx.Response(200, json={"status": state["status"]})

    a_client(handler).wait("run-1")

    assert sent == [
        {"decisions": [{"index": 0, "type": "respond", "message": RESPOND_MESSAGE}]}
    ]


def test_memory_usage_waits_for_the_async_job_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run.finished 早于抽取 job，queued/running 时取账会漏掉成本。"""
    states = iter(("queued", "running", "succeeded"))
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "job_status": next(states),
                "selector": {"model": "aux", "cost_yuan": 0.1},
                "extractor": None,
                "consolidator": None,
            },
        )

    monkeypatch.setattr("client.time.sleep", lambda _seconds: None)

    result = a_client(handler).wait_memory_usage("run-1")

    assert calls == 3
    assert result["job_status"] == "succeeded"


def test_memory_usage_terminal_failure_is_returned_for_auditing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "job_status": "failed",
                "selector": None,
                "extractor": {"model": "aux", "cost_yuan": 0.2},
                "consolidator": {"model": "aux", "cost_yuan": 0.0},
            },
        )

    result = a_client(handler).wait_memory_usage("run-1")

    assert result["job_status"] == "failed"
