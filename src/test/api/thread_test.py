from functools import partial
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.platform import Platform
from app.auth.password import PasswordHasher
from app.event.model import RunStatus
from app.sandbox.workspace import Workspace
from test.api.conftest import FAKE_TITLE, Agent, FakePool, drain, login, signup

# 工作目录里的文件（上传、列结构、预览、下载、删除）全部在 file_test.py


def _become_someone_else(client: TestClient, platform: Platform, hasher: PasswordHasher) -> None:
    """换成另一个人登录。同一个客户端，换一份 Cookie。"""
    name = f"other-{uuid4().hex[:8]}"
    signup(client, platform, hasher, name=name)
    client.cookies.clear()
    login(client, name)


# ------------------------------------------------------------------ 列表携带进行中状态
def test_a_thread_without_live_runs_reports_none(client: TestClient, thread_id: str) -> None:
    page = client.get("/api/threads").json()
    mine = next(one for one in page["items"] if one["id"] == thread_id)

    assert mine["live_run_status"] is None


def test_thread_list_reports_the_live_run_status(client: TestClient, platform: Platform, thread_id: str) -> None:
    """会话侧栏的「进行中」状态点：列表响应带上还在跑的 run 的状态。

    直接落一行 queued 的 run（不进队列，worker 不会碰它），状态稳定可断言 ——
    走提交路径的话 worker 会把它跑完，断言就在跟执行竞速。
    """
    user = client.get("/api/auth/me").json()
    assert client.portal is not None
    client.portal.call(
        partial(
            platform.repository.create,
            run_id=uuid4().hex,
            thread_id=thread_id,
            user_id=user["id"],
        )
    )

    page = client.get("/api/threads").json()
    mine = next(one for one in page["items"] if one["id"] == thread_id)
    assert mine["live_run_status"] == RunStatus.QUEUED


# ------------------------------------------------------------------ 建会话
def test_creating_a_thread_returns_its_id(client: TestClient) -> None:
    response = client.post("/api/threads")

    assert response.status_code == 201
    assert response.json()["id"]


def test_each_thread_gets_a_distinct_id(client: TestClient) -> None:
    first = client.post("/api/threads").json()["id"]
    second = client.post("/api/threads").json()["id"]

    assert first != second


def test_a_created_thread_has_a_workspace(client: TestClient, space: Workspace) -> None:
    thread_id = client.post("/api/threads").json()["id"]

    assert space.exists(thread_id)


# ------------------------------------------------------------------ 提交分析
def test_submitting_a_run_returns_202_immediately(client: TestClient, thread_id: str) -> None:
    """任务要跑几十分钟，提交不能等它完成。"""
    response = client.post(f"/api/threads/{thread_id}/runs", json={"content": "算个波动率"})

    assert response.status_code == 202
    assert response.json()["thread_id"] == thread_id
    assert response.json()["status"] == RunStatus.QUEUED.value


def test_the_question_reaches_the_agent(client: TestClient, thread_id: str, agent: Agent) -> None:
    run_id = client.post(f"/api/threads/{thread_id}/runs", json={"content": "按行业分组算年化波动率"}).json()["id"]
    drain(client, run_id)

    assert agent.asked == ["按行业分组算年化波动率"]


def test_submitting_to_an_unknown_thread_is_not_found(client: TestClient) -> None:
    response = client.post("/api/threads/never-created/runs", json={"content": "一"})

    assert response.status_code == 404


def test_an_empty_question_is_rejected(client: TestClient, thread_id: str) -> None:
    response = client.post(f"/api/threads/{thread_id}/runs", json={"content": ""})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_a_missing_body_is_rejected(client: TestClient, thread_id: str) -> None:
    response = client.post(f"/api/threads/{thread_id}/runs")

    assert response.status_code == 422


def test_a_thread_id_that_escapes_the_root_is_not_found(client: TestClient) -> None:
    """会话标识参与拼路径，非法值的回答该是 404 而不是 500。"""
    response = client.post("/api/threads/..%2F..%2Fetc/runs", json={"content": "一"})

    assert response.status_code == 404


# ------------------------------------------------------------------ 会话列表
def test_the_list_shows_the_threads_i_created(client: TestClient) -> None:
    first = client.post("/api/threads").json()["id"]
    second = client.post("/api/threads").json()["id"]

    items = client.get("/api/threads").json()["items"]

    assert [one["id"] for one in items] == [second, first]


def test_the_list_puts_the_thread_i_just_used_on_top(client: TestClient, thread_id: str) -> None:
    """侧边栏最上面该是刚问过问题的那个，而不是最后建的那个。"""
    client.post("/api/threads")
    client.post(f"/api/threads/{thread_id}/runs", json={"content": "算个波动率"})

    items = client.get("/api/threads").json()["items"]

    assert items[0]["id"] == thread_id


def test_the_list_does_not_show_someone_elses_threads(
    client: TestClient, platform: Platform, hasher: PasswordHasher
) -> None:
    """隔离长在仓储那一层，端点这里一句鉴权判断都没有。"""
    mine = client.post("/api/threads").json()["id"]
    _become_someone_else(client, platform, hasher)

    items = client.get("/api/threads").json()["items"]

    assert [one["id"] for one in items] == []
    assert mine not in [one["id"] for one in items]


def test_the_list_pages_with_a_cursor(client: TestClient) -> None:
    created = [client.post("/api/threads").json()["id"] for _ in range(3)]

    seen: list[str] = []
    cursor: str | None = None
    while True:
        query = {"limit": 2} | ({"cursor": cursor} if cursor else {})
        page = client.get("/api/threads", params=query).json()
        seen.extend(one["id"] for one in page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            break

    assert seen == list(reversed(created))


def test_a_garbage_cursor_is_rejected(client: TestClient) -> None:
    """当成「从头开始」的话，前端会收到一整页重复数据而看不出发生了什么。"""
    response = client.get("/api/threads", params={"cursor": "不是游标"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_an_over_sized_page_is_rejected(client: TestClient) -> None:
    """放开的话一次请求就能把整段历史拉出来。"""
    assert client.get("/api/threads", params={"limit": 10_000}).status_code == 422


def test_the_list_can_be_searched_by_title(client: TestClient) -> None:
    """标题模糊搜索：只命中含关键词的会话，别的原样保留。"""
    first = client.post("/api/threads").json()["id"]
    client.patch(f"/api/threads/{first}", json={"title": "波动率分析"})
    second = client.post("/api/threads").json()["id"]
    client.patch(f"/api/threads/{second}", json={"title": "债券收益率复盘"})

    hit = client.get("/api/threads", params={"q": "波动"}).json()["items"]

    assert [one["id"] for one in hit] == [first]

    none = client.get("/api/threads", params={"q": "不存在的话题"}).json()["items"]
    assert none == []


def test_an_over_long_search_query_is_rejected(client: TestClient) -> None:
    assert client.get("/api/threads", params={"q": "长" * 65}).status_code == 422


# ------------------------------------------------------------------ 详情与改
def test_a_thread_detail_carries_its_agent_config(client: TestClient, thread_id: str) -> None:
    response = client.get(f"/api/threads/{thread_id}")

    assert response.status_code == 200
    assert response.json()["agent_config"] == {}


def test_someone_elses_thread_is_not_found(
    client: TestClient, thread_id: str, platform: Platform, hasher: PasswordHasher
) -> None:
    _become_someone_else(client, platform, hasher)

    assert client.get(f"/api/threads/{thread_id}").status_code == 404


def test_the_title_can_be_renamed(client: TestClient, thread_id: str) -> None:
    response = client.patch(f"/api/threads/{thread_id}", json={"title": "我自己起的名"})

    assert response.status_code == 200
    assert response.json()["title"] == "我自己起的名"


def test_renaming_leaves_the_agent_config_alone(client: TestClient, thread_id: str) -> None:
    """一次改名把 agent 配置清空，是那种改完当时没事、下次跑分析才发现的故障。"""
    client.patch(f"/api/threads/{thread_id}", json={"agent_config": {"system_prompt": "只用新闻口径"}})

    response = client.patch(f"/api/threads/{thread_id}", json={"title": "只改标题"})

    assert response.json()["agent_config"] == {"system_prompt": "只用新闻口径"}


def test_an_unknown_agent_config_field_is_rejected(client: TestClient, thread_id: str) -> None:
    response = client.patch(f"/api/threads/{thread_id}", json={"agent_config": {"model": "aux"}})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_an_over_long_agent_prompt_is_rejected(client: TestClient, thread_id: str) -> None:
    response = client.patch(f"/api/threads/{thread_id}", json={"agent_config": {"system_prompt": "角" * 4001}})

    assert response.status_code == 422


def test_an_over_long_title_is_rejected(client: TestClient, thread_id: str) -> None:
    response = client.patch(f"/api/threads/{thread_id}", json={"title": "标" * 500})

    assert response.status_code == 422


def test_renaming_an_unknown_thread_is_not_found(client: TestClient) -> None:
    assert client.patch("/api/threads/never-created", json={"title": "一"}).status_code == 404


# ------------------------------------------------------------------ 删会话
def test_a_deleted_thread_is_gone_from_the_list(client: TestClient, thread_id: str) -> None:
    assert client.delete(f"/api/threads/{thread_id}").status_code == 204

    items = client.get("/api/threads").json()["items"]
    assert thread_id not in [one["id"] for one in items]


def test_a_deleted_thread_is_not_found(client: TestClient, thread_id: str) -> None:
    client.delete(f"/api/threads/{thread_id}")

    assert client.get(f"/api/threads/{thread_id}").status_code == 404


def test_deleting_the_same_thread_twice_is_not_found(client: TestClient, thread_id: str) -> None:
    """**第二下是 404 而不是 204。**

    答 204 等于确认了「这个 id 曾经存在过」，而整个平台的口径是「不存在」与
    「不属于你」给同一个回答 —— 否则这条端点就成了探测别人有哪些会话的工具。
    """
    client.delete(f"/api/threads/{thread_id}")

    assert client.delete(f"/api/threads/{thread_id}").status_code == 404


def test_deleting_a_thread_removes_its_workspace(client: TestClient, thread_id: str, space: Workspace) -> None:
    """磁盘也要真的还回来 —— 「从列表里消失」只解决了一半。"""
    client.delete(f"/api/threads/{thread_id}")

    assert space.exists(thread_id) is False


def test_a_workspace_destroy_failure_keeps_a_persistent_retry_job(
    client: TestClient,
    thread_id: str,
    platform: Platform,
    space: Workspace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """非预期的 broker 异常也不能丢待办，或把已软删会话误报成未删。"""

    async def fail_destroy(_thread_id: str) -> None:
        raise RuntimeError("模拟销毁尾声异常")

    monkeypatch.setattr(platform.workspace, "destroy", fail_destroy)

    response = client.delete(f"/api/threads/{thread_id}")

    assert response.status_code == 204
    assert client.get(f"/api/threads/{thread_id}").status_code == 404
    assert space.exists(thread_id) is True
    assert client.portal is not None
    pending = [one for one in client.portal.call(platform.thread.pending_purge) if one.thread_id == thread_id]
    assert [(one.thread_id, one.attempts, one.last_error) for one in pending] == [(thread_id, 1, "模拟销毁尾声异常")]


def test_deleting_a_thread_destroys_its_sandbox(
    client: TestClient, thread_id: str, pool: FakePool, agent: Agent
) -> None:
    """容器留着就是挂在一个已经被删掉的目录上。"""
    run_id = client.post(f"/api/threads/{thread_id}/runs", json={"content": "一"}).json()["id"]
    drain(client, run_id)

    client.delete(f"/api/threads/{thread_id}")

    assert thread_id in pool.discarded


def test_deleting_someone_elses_thread_is_not_found(
    client: TestClient, thread_id: str, platform: Platform, hasher: PasswordHasher, space: Workspace
) -> None:
    _become_someone_else(client, platform, hasher)

    assert client.delete(f"/api/threads/{thread_id}").status_code == 404
    assert space.exists(thread_id) is True


def test_a_deleted_thread_keeps_its_run_history_in_the_ledger(
    client: TestClient, thread_id: str, platform: Platform
) -> None:
    """软删除的理由：`runs` 是成本账本，删掉等于往历史里挖一个洞。"""
    run_id = client.post(f"/api/threads/{thread_id}/runs", json={"content": "一"}).json()["id"]

    client.delete(f"/api/threads/{thread_id}")

    assert client.get(f"/api/runs/{run_id}").status_code == 200


# ------------------------------------------------------------------ 聊天历史
def test_the_history_carries_the_question_that_was_asked(client: TestClient, thread_id: str) -> None:
    """事件流里没有承载提问的事件 —— 用户那一侧的气泡只能从这里来。"""
    client.post(f"/api/threads/{thread_id}/runs", json={"content": "按行业分组算年化波动率"})

    items = client.get(f"/api/threads/{thread_id}/runs").json()["items"]

    assert [one["content"] for one in items] == ["按行业分组算年化波动率"]


def test_the_history_gives_the_newest_first(client: TestClient, thread_id: str) -> None:
    client.post(f"/api/threads/{thread_id}/runs", json={"content": "第一问"})
    client.post(f"/api/threads/{thread_id}/runs", json={"content": "第二问"})

    items = client.get(f"/api/threads/{thread_id}/runs").json()["items"]

    assert [one["content"] for one in items] == ["第二问", "第一问"]


def test_the_history_carries_the_outcome_of_each_run(client: TestClient, thread_id: str, agent: Agent) -> None:
    """前端据此决定这一轮显示结果、报错还是重试按钮。"""
    run_id = client.post(f"/api/threads/{thread_id}/runs", json={"content": "一"}).json()["id"]
    drain(client, run_id)

    items = client.get(f"/api/threads/{thread_id}/runs").json()["items"]

    assert items[0]["status"] == RunStatus.SUCCEEDED.value
    assert items[0]["ended_at"] is not None


def test_the_history_of_someone_elses_thread_is_not_found(
    client: TestClient, thread_id: str, platform: Platform, hasher: PasswordHasher
) -> None:
    _become_someone_else(client, platform, hasher)

    assert client.get(f"/api/threads/{thread_id}/runs").status_code == 404


def test_the_history_pages_with_a_cursor(client: TestClient, thread_id: str) -> None:
    asked = ["一", "二", "三"]
    for one in asked:
        client.post(f"/api/threads/{thread_id}/runs", json={"content": one})

    seen: list[str] = []
    cursor: str | None = None
    while True:
        query = {"limit": 2} | ({"cursor": cursor} if cursor else {})
        page = client.get(f"/api/threads/{thread_id}/runs", params=query).json()
        seen.extend(one["content"] for one in page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            break

    assert seen == list(reversed(asked))


# ------------------------------------------------------------------ 自动起标题
def test_the_first_question_gives_the_thread_a_title(client: TestClient, thread_id: str) -> None:
    """教师不必先给会话起名 —— 那道门槛多数人会跳过，于是侧边栏变成一排「未命名」。"""
    assert client.get(f"/api/threads/{thread_id}").json()["title"] == ""

    client.post(f"/api/threads/{thread_id}/runs", json={"content": "按行业分组算年化波动率"})

    assert client.get(f"/api/threads/{thread_id}").json()["title"] == FAKE_TITLE


def test_a_later_question_does_not_rename_the_thread(client: TestClient, thread_id: str) -> None:
    """只有第一次值得花这一次调用。每次都起等于每次提交都多一次模型往返。"""
    client.patch(f"/api/threads/{thread_id}", json={"title": "我自己起的名"})

    client.post(f"/api/threads/{thread_id}/runs", json={"content": "一"})

    assert client.get(f"/api/threads/{thread_id}").json()["title"] == "我自己起的名"
