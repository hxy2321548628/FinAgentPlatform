"""用量端点：没接账本时说得出「没接」，接上了给的是真数。"""

from fastapi.testclient import TestClient

from test.api.conftest import as_admin

MY_PATH = "/api/usage/me"

RANKING_PATH = "/api/usage/ranking"


def test_without_a_ledger_it_says_so_instead_of_reporting_zero(client: TestClient) -> None:
    """**「没接账本」与「这个月还没人用」必须分得开。**

    两者都回一串 0 的话，教师看到「本月用量 0」时无从判断是自己真没用过，
    还是平台根本没在记 —— 而这两件事一个什么都不用做，一个要去配环境。
    测试环境没有 Langfuse，因此这里走的正是「没接」那一支。
    """
    response = client.get(MY_PATH)

    assert response.status_code == 200, response.text
    assert response.json()["available"] is False


def test_the_ranking_is_admin_only(client: TestClient) -> None:
    """排行透出的是别人的用量，不是自己的。"""
    assert client.get(RANKING_PATH).status_code == 403


def test_an_admin_can_open_the_ranking(client: TestClient, admin: str) -> None:
    as_admin(client, admin)

    response = client.get(RANKING_PATH)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["available"] is False
    assert body["items"] == []


def test_my_usage_needs_a_session(client: TestClient) -> None:
    """用量是个人数据，未登录看不到。"""
    client.cookies.clear()

    assert client.get(MY_PATH).status_code == 401
