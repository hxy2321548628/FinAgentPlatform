"""平台客户端的测试。

**批准那一段值得单测**：一次中断可能停下不止一个调用，少批一个是 422，
而那个红看着像 agent 没做好 —— 首轮就是这么白跑了一道题。
"""

import httpx
from client import PlatformClient


def a_client(handler: object) -> PlatformClient:
    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    return PlatformClient(base_url="http://platform", client=httpx.Client(transport=transport))


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
                                        {"index": 0, "tool_name": "delete", "allowed_decisions": ["approve", "reject"]},
                                        {"index": 1, "tool_name": "delete", "allowed_decisions": ["approve"]},
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
    assert sent == [{"decisions": [{"index": 0, "type": "approve"}, {"index": 1, "type": "approve"}]}]


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
                                "data": {"actions": [{"index": 0, "allowed_decisions": ["reject"]}]},
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
        return httpx.Response(200, json={"status": "waiting_approval" if calls["poll"] < 2 else "succeeded"})

    status, approvals = a_client(handler).wait("run-1")

    assert status == "succeeded"
    assert calls["approve"] == 0
    assert approvals == 0
