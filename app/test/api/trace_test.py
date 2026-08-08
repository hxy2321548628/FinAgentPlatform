"""一个 run 的 trace 要跨过队列连成一条。

**这是链路追踪里唯一不能靠单测保证的接缝。** `telemetry/context.py` 那几条验的是
「给我一个 carrier，我能接上」；这里验的是**真的走了那条路** —— 提交端点把上下文放进了
任务消息、worker 又真的从消息里取了出来。中间任何一处漏掉都不会报错，
只会让每个 run 断成互不相干的两条 trace。

这套夹具里 worker 与 api 恰好同进程，但**中间仍然是真的 Redis Stream**：
worker 的主循环跑在自己的任务里，它的上下文是夹具建立时复制的那一份，
不是这次 POST 的 —— 因此「同进程」并不会让这条用例假过。

**断言之前要等一下那个 span。** worker 的 `run.execute` 是在终态事件发出去**之后**
才结束的（`with` 块还要退栈、归还沙箱），而 `drain()` 读到终态就返回了 ——
两者之间差着几百微秒。实测直接断言会以三分之一左右的概率红在「一个都没有」上，
而那个报错看起来跟传播完全无关。
"""

import time

from fastapi.testclient import TestClient
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from telemetry.run import RUN_ATTRIBUTE, SPAN_NAME
from test.api.conftest import Agent, drain

SUBMIT_ROUTE = "/api/threads/{thread_id}/runs"
SANDBOX_ROUTE = "/threads/{thread_id}/sandbox"

# 等 span 收尾的上限。实测差几百微秒，给到秒级是为了让慢机器上也不会偶发红 ——
# 正常情况下第一次轮询就拿到了，这个数不构成用例时长
SPAN_WAIT_SECOND = 5.0
POLL_SECOND = 0.01


def trace_of(span: ReadableSpan) -> int:
    assert span.context is not None
    trace_id: int = span.context.trace_id
    return trace_id


def worker_span(exporter: InMemorySpanExporter, run_id: str) -> ReadableSpan:
    """本次 run 在 worker 侧的那个 span，**等到它收尾为止**。

    按 run_id 挑而不按名字数：上一条用例的 span 同样可能刚好落进这个窗口。
    """
    deadline = time.monotonic() + SPAN_WAIT_SECOND
    found: list[ReadableSpan] = []
    while not found and time.monotonic() < deadline:
        found = [
            one
            for one in exporter.get_finished_spans()
            if one.name == SPAN_NAME and dict(one.attributes or {}).get(RUN_ATTRIBUTE) == run_id
        ]
        if not found:
            time.sleep(POLL_SECOND)
    assert len(found) == 1, f"按 {RUN_ATTRIBUTE}={run_id} 该挑出恰好一个 {SPAN_NAME}，实际 {len(found)} 个"
    return found[0]


def same_trace(exporter: InMemorySpanExporter, span: ReadableSpan, route: str) -> list[ReadableSpan]:
    """与给定 span 同一条 trace、且落在指定路由上的那些 span。"""
    return [
        one
        for one in exporter.get_finished_spans()
        if route in one.name and one.context is not None and one.context.trace_id == trace_of(span)
    ]


def a_run(client: TestClient, thread_id: str, agent: Agent) -> str:
    agent.chunk = []
    run_id: str = client.post(f"/api/threads/{thread_id}/runs", json={"content": "问题"}).json()["id"]
    drain(client, run_id)
    return run_id


def test_the_worker_side_span_joins_the_trace_the_gateway_started(
    client: TestClient, thread_id: str, agent: Agent, recorded_span: InMemorySpanExporter
) -> None:
    """**整条链路上唯一手接的那一跳。**

    断的是「与 worker 那个 span 同一条 trace 里有没有网关那一段」—— 传播断掉时
    worker 会自己开一条新 trace，那一边就一个都挑不出来。「两个 span 都在」
    证明不了它们串上了。
    """
    run_id = a_run(client, thread_id, agent)

    assert same_trace(recorded_span, worker_span(recorded_span, run_id), SUBMIT_ROUTE)


def test_the_run_id_is_searchable_on_the_worker_span(
    client: TestClient, thread_id: str, agent: Agent, recorded_span: InMemorySpanExporter
) -> None:
    """验收 ① 的入口就是这个属性：给一个 run_id，找到那条 trace。"""
    run_id = a_run(client, thread_id, agent)

    assert dict(worker_span(recorded_span, run_id).attributes or {})[RUN_ATTRIBUTE] == run_id


def test_the_broker_endpoints_produce_spans_of_their_own(
    client: TestClient, thread_id: str, agent: Agent, recorded_span: InMemorySpanExporter
) -> None:
    """沙箱那几跳在 trace 上要有自己的 span，否则「sandbox 段耗时」无处可看。

    **这一条只证明 broker 的应用挂上了探针，不证明跨进程传播成立。** 这套夹具里
    broker 与 worker 同进程同任务，上下文靠 contextvars 就传过去了 —— 即使把
    httpx 探针整个拆掉，下面的断言照样绿。**跨进程那一半只有 compose 全栈能验**
    （验收 ①），这里刻意不假装验到了它。
    """
    run_id = a_run(client, thread_id, agent)

    assert same_trace(recorded_span, worker_span(recorded_span, run_id), SANDBOX_ROUTE)
