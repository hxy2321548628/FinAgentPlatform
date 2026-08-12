"""`files/raw` 的 nginx 直发那条路。

**单独成文件是因为夹具**：`file_direct_send` 一旦定义在模块里就对整个模块生效，
放进 `file_test.py` 会把那一包本来验「api 自己转发」的用例一起改掉 ——
两条路都要有人验，而它们的差别正是响应体里有没有字节。

用例里没有 nginx，因此验的是「交给它的那张条子对不对」，不是字节本身。
"""

import pytest
from fastapi.testclient import TestClient

from sandbox.workspace import Workspace
from test.api.file_test import make


@pytest.fixture
def file_direct_send() -> bool:
    return True


def test_direct_send_hands_the_bytes_to_nginx_instead_of_streaming_them(
    client: TestClient, thread_id: str, space: Workspace
) -> None:
    """响应体是空的 —— api 进程一个字节都不经手，这正是直发的全部意义。"""
    make(space, thread_id, "outputs/chart.png", b"png-bytes")

    response = client.get(f"/api/threads/{thread_id}/files/raw", params={"path": "outputs/chart.png"})

    assert response.status_code == 200
    assert response.headers["x-accel-redirect"] == f"/workspace/{thread_id}/outputs/chart.png"
    assert response.headers["content-type"] == "image/png"
    assert response.content == b""


def test_direct_send_hands_over_the_normalized_path_not_the_requested_one(
    client: TestClient, thread_id: str, space: Workspace
) -> None:
    """`./` 这类必须在这一侧化掉。原样转给 nginx 等于让它自己去解释路径。"""
    make(space, thread_id, "outputs/chart.png", b"png-bytes")

    response = client.get(f"/api/threads/{thread_id}/files/raw", params={"path": "outputs/./chart.png"})

    assert response.headers["x-accel-redirect"] == f"/workspace/{thread_id}/outputs/chart.png"


def test_direct_send_escapes_a_chinese_filename(client: TestClient, thread_id: str, space: Workspace) -> None:
    """这个头会被 nginx 做一次 unescape，不编码的话中文文件名到它那里就散了。"""
    make(space, thread_id, "持仓明细.csv", b"a,b\n")

    response = client.get(f"/api/threads/{thread_id}/files/raw", params={"path": "持仓明细.csv"})

    assert response.headers["x-accel-redirect"] == (f"/workspace/{thread_id}/%E6%8C%81%E4%BB%93%E6%98%8E%E7%BB%86.csv")


def test_direct_send_still_asks_the_browser_to_save_it(client: TestClient, thread_id: str, space: Workspace) -> None:
    """Content-Disposition 由 api 给，nginx 只负责补上字节。"""
    make(space, thread_id, "持仓明细.csv", b"a,b\n")

    response = client.get(f"/api/threads/{thread_id}/files/raw", params={"path": "持仓明细.csv", "download": True})

    assert (
        response.headers["content-disposition"]
        == "attachment; filename*=UTF-8''%E6%8C%81%E4%BB%93%E6%98%8E%E7%BB%86.csv"
    )


@pytest.mark.parametrize("path", ["never-made.png", "../../etc/passwd", "/etc/passwd"])
def test_direct_send_does_not_loosen_the_path_check(client: TestClient, thread_id: str, path: str) -> None:
    """开了直发也不能有任何一条路径绕过 broker 的判定。

    **这一条是这组里最要紧的**：绕过去的话，nginx 会照着一张没人验过的条子
    去读宿主机上的文件。
    """
    response = client.get(f"/api/threads/{thread_id}/files/raw", params={"path": path})

    assert response.status_code == 404
    assert "x-accel-redirect" not in response.headers


def test_direct_send_refuses_a_directory(client: TestClient, thread_id: str, space: Workspace) -> None:
    make(space, thread_id, "outputs/chart.png", b"png")

    response = client.get(f"/api/threads/{thread_id}/files/raw", params={"path": "outputs"})

    assert response.status_code == 422
    assert "x-accel-redirect" not in response.headers
