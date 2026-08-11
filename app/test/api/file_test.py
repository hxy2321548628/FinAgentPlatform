"""会话工作目录的对外端点：列结构、看内容、下载、上传、删除。

**api 与 broker 之间走真的 HTTP**（见 conftest），因此这一整包同时也验了
「字节确实经 broker 转出来」这条路 —— 用假 workspace 顶掉的话，要验的正好没验。
"""

import io

import pytest
from fastapi.testclient import TestClient

from sandbox.workspace import Workspace


def upload(client: TestClient, thread_id: str, filename: str, content: bytes = b"a,b\n", **form: str) -> object:
    return client.post(
        f"/api/threads/{thread_id}/files",
        files={"file": (filename, io.BytesIO(content), "text/csv")},
        data=form,
    )


def make(space: Workspace, thread_id: str, relative: str, content: bytes) -> None:
    target = space.path(thread_id) / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)


def tree(client: TestClient, thread_id: str) -> object:
    return client.get(f"/api/threads/{thread_id}/files")


# ------------------------------------------------------------------ 目录结构
def test_the_tree_lists_what_is_in_the_workspace(client: TestClient, thread_id: str, space: Workspace) -> None:
    make(space, thread_id, "analyze.py", b"print(1)\n")
    make(space, thread_id, "outputs/chart.png", b"png")

    response = tree(client, thread_id)

    assert response.status_code == 200  # type: ignore[attr-defined]
    assert [one["path"] for one in response.json()["entries"]] == [  # type: ignore[attr-defined]
        "analyze.py",
        "outputs",
        "outputs/chart.png",
    ]


def test_a_directory_is_marked_so_the_sidebar_can_draw_a_folder(
    client: TestClient, thread_id: str, space: Workspace
) -> None:
    make(space, thread_id, "outputs/chart.png", b"png")

    entries = {one["path"]: one["is_dir"] for one in tree(client, thread_id).json()["entries"]}  # type: ignore[attr-defined]

    assert entries == {"outputs": True, "outputs/chart.png": False}


def test_an_entry_carries_its_size_and_time(client: TestClient, thread_id: str, space: Workspace) -> None:
    make(space, thread_id, "holdings.csv", b"a,b\n")

    entry = tree(client, thread_id).json()["entries"][0]  # type: ignore[attr-defined]

    assert entry["size"] == 4
    assert entry["modified_at"]


def test_a_fresh_thread_has_an_empty_tree(client: TestClient, thread_id: str) -> None:
    assert tree(client, thread_id).json() == {"entries": [], "truncated": False}  # type: ignore[attr-defined]


def test_the_tree_of_an_unknown_thread_is_not_found(client: TestClient) -> None:
    assert tree(client, "never-created").status_code == 404  # type: ignore[attr-defined]


# ------------------------------------------------------------------ 看内容
def test_reading_a_code_file_gives_its_text(client: TestClient, thread_id: str, space: Workspace) -> None:
    make(space, thread_id, "analyze.py", b"import pandas\nprint(1)\n")

    response = client.get(f"/api/threads/{thread_id}/files/content", params={"path": "analyze.py"})

    assert response.status_code == 200
    assert response.json()["text"] == "import pandas\nprint(1)"
    assert response.json()["total_line"] == 2


def test_a_window_can_start_partway_down(client: TestClient, thread_id: str, space: Workspace) -> None:
    """几十万行的 csv 不能一次全发过来。"""
    make(space, thread_id, "big.csv", "一\n二\n三\n四\n".encode())

    found = client.get(
        f"/api/threads/{thread_id}/files/content", params={"path": "big.csv", "offset": 2, "limit": 1}
    ).json()

    assert found["text"] == "三"
    assert (found["start_line"], found["end_line"]) == (3, 3)


def test_a_binary_file_is_flagged_rather_than_garbled(client: TestClient, thread_id: str, space: Workspace) -> None:
    make(space, thread_id, "outputs/chart.png", b"\x89PNG\r\n\x1a\n\x00\x00")

    found = client.get(f"/api/threads/{thread_id}/files/content", params={"path": "outputs/chart.png"}).json()

    assert found["is_binary"]
    assert found["text"] == ""


def test_reading_a_directory_is_a_validation_error(client: TestClient, thread_id: str, space: Workspace) -> None:
    """目录在树里看得见，说出来不泄露任何东西 —— 这一条不必伪装成 404。"""
    make(space, thread_id, "outputs/chart.png", b"png")

    response = client.get(f"/api/threads/{thread_id}/files/content", params={"path": "outputs"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_reading_a_missing_file_is_not_found(client: TestClient, thread_id: str) -> None:
    response = client.get(f"/api/threads/{thread_id}/files/content", params={"path": "never-made.py"})

    assert response.status_code == 404


@pytest.mark.parametrize("path", ["../../etc/passwd", "/etc/passwd", "../holdings.csv"])
def test_reading_outside_the_workspace_reads_as_missing(client: TestClient, thread_id: str, path: str) -> None:
    """越界与不存在给同一个回答，否则这个端点就成了探测宿主机文件的工具。"""
    response = client.get(f"/api/threads/{thread_id}/files/content", params={"path": path})

    assert response.status_code == 404


# 越权（拿别人的身份够这些端点）全部集中在 isolation_test.py —— 那里逐条列着
# 每一个能被够到的路径，散在各处的话漏掉一条不会有人发现


# ------------------------------------------------------------------ 下载
def test_a_file_comes_back_byte_for_byte(client: TestClient, thread_id: str, space: Workspace) -> None:
    make(space, thread_id, "outputs/chart.png", b"\x89PNG binary")

    response = client.get(f"/api/threads/{thread_id}/files/raw", params={"path": "outputs/chart.png"})

    assert response.status_code == 200
    assert response.content == b"\x89PNG binary"


def test_a_download_carries_its_content_type(client: TestClient, thread_id: str, space: Workspace) -> None:
    """前端拿它决定是塞进 <img> 还是当文本读。"""
    make(space, thread_id, "outputs/chart.png", b"png")

    response = client.get(f"/api/threads/{thread_id}/files/raw", params={"path": "outputs/chart.png"})

    assert response.headers["content-type"] == "image/png"


def test_by_default_a_file_is_shown_inline_not_saved(client: TestClient, thread_id: str, space: Workspace) -> None:
    """图片要能直接塞进 <img>，带上 attachment 就变成一次下载了。"""
    make(space, thread_id, "outputs/chart.png", b"png")

    response = client.get(f"/api/threads/{thread_id}/files/raw", params={"path": "outputs/chart.png"})

    assert "content-disposition" not in response.headers


def test_asking_to_download_makes_the_browser_save_it(client: TestClient, thread_id: str, space: Workspace) -> None:
    make(space, thread_id, "持仓明细.csv", b"a,b\n")

    response = client.get(f"/api/threads/{thread_id}/files/raw", params={"path": "持仓明细.csv", "download": True})

    # 中文文件名只能走 RFC 5987 的 filename*，老式的 filename= 只认 latin-1
    assert (
        response.headers["content-disposition"]
        == "attachment; filename*=UTF-8''%E6%8C%81%E4%BB%93%E6%98%8E%E7%BB%86.csv"
    )


def test_downloading_a_missing_file_is_not_found(client: TestClient, thread_id: str) -> None:
    response = client.get(f"/api/threads/{thread_id}/files/raw", params={"path": "never-made.png"})

    assert response.status_code == 404


@pytest.mark.parametrize("path", ["../../etc/passwd", "/etc/passwd"])
def test_downloading_outside_the_workspace_reads_as_missing(client: TestClient, thread_id: str, path: str) -> None:
    assert client.get(f"/api/threads/{thread_id}/files/raw", params={"path": path}).status_code == 404


# ------------------------------------------------------------------ 上传
def test_uploading_a_file_lands_it_in_the_workspace(client: TestClient, thread_id: str, space: Workspace) -> None:
    response = upload(client, thread_id, "holdings.csv")

    assert response.status_code == 201  # type: ignore[attr-defined]
    assert (space.path(thread_id) / "holdings.csv").read_bytes() == b"a,b\n"


def test_the_upload_response_reports_what_landed(client: TestClient, thread_id: str) -> None:
    response = upload(client, thread_id, "holdings.csv", b"a,b\nc,d\n")

    assert response.json() == {"filename": "holdings.csv", "path": "holdings.csv", "size": 8}  # type: ignore[attr-defined]


def test_a_second_file_needs_a_second_request(client: TestClient, thread_id: str, space: Workspace) -> None:
    """一次一个 —— 前端一个一个发，逐个有自己的进度与重试。"""
    upload(client, thread_id, "one.csv", b"1")
    upload(client, thread_id, "two.csv", b"2")

    assert (space.path(thread_id) / "one.csv").read_bytes() == b"1"
    assert (space.path(thread_id) / "two.csv").read_bytes() == b"2"


def test_a_file_can_go_into_an_existing_subdirectory(client: TestClient, thread_id: str, space: Workspace) -> None:
    (space.path(thread_id) / "data").mkdir()

    response = upload(client, thread_id, "holdings.csv", directory="data")

    assert response.json()["path"] == "data/holdings.csv"  # type: ignore[attr-defined]
    assert (space.path(thread_id) / "data" / "holdings.csv").exists()


def test_the_landed_path_is_not_just_directory_plus_filename(
    client: TestClient, thread_id: str, space: Workspace
) -> None:
    """文件名会被收成末段，靠 `directory + filename` 拼是拼不出真正落盘的那个的。"""
    (space.path(thread_id) / "data").mkdir()

    response = upload(client, thread_id, "sub/dir/holdings.csv", directory="data")

    assert response.json()["path"] == "data/holdings.csv"  # type: ignore[attr-defined]


def test_uploading_into_a_directory_that_is_not_there_is_rejected(client: TestClient, thread_id: str) -> None:
    """目录来自侧边栏上的一次点击，点得到就说明它在 —— 不在就是请求本身不对。"""
    response = upload(client, thread_id, "holdings.csv", directory="never-made")

    assert response.status_code == 404  # type: ignore[attr-defined]


def test_uploading_to_an_unknown_thread_is_not_found(client: TestClient) -> None:
    response = upload(client, "never-created", "holdings.csv")

    assert response.status_code == 404  # type: ignore[attr-defined]
    assert response.json()["error"]["code"] == "NOT_FOUND"  # type: ignore[attr-defined]


def test_a_traversing_filename_cannot_escape_the_workspace(
    client: TestClient, thread_id: str, space: Workspace
) -> None:
    """文件名来自 HTTP 请求，是不可信输入。"""
    upload(client, thread_id, "../../escaped.csv")

    assert not (space.path(thread_id).parent.parent / "escaped.csv").exists()


@pytest.mark.parametrize("directory", ["..", "../elsewhere", "/etc"])
def test_a_traversing_directory_cannot_escape_the_workspace(client: TestClient, thread_id: str, directory: str) -> None:
    response = upload(client, thread_id, "holdings.csv", directory=directory)

    assert response.status_code == 404  # type: ignore[attr-defined]


def test_uploading_without_a_file_is_a_validation_error(client: TestClient, thread_id: str) -> None:
    response = client.post(f"/api/threads/{thread_id}/files")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_a_filename_with_no_usable_segment_is_rejected(client: TestClient, thread_id: str) -> None:
    """`..` 收成末段之后什么都不剩，落不了盘。"""
    response = upload(client, thread_id, "..")

    assert response.status_code == 404  # type: ignore[attr-defined]
    assert response.json()["error"]["code"] == "NOT_FOUND"  # type: ignore[attr-defined]


def test_a_failed_upload_is_not_a_2xx(client: TestClient, thread_id: str) -> None:
    """`curl -fsS` 那类「非 2xx 才算失败」的调用方靠这一条 —— 验收脚本正是这么判的。"""
    assert not upload(client, thread_id, "..").is_success  # type: ignore[attr-defined]


def test_only_one_file_lands_and_the_response_names_it(client: TestClient, thread_id: str, space: Workspace) -> None:
    """端点收一个文件，一个请求塞几个时框架只取一个。

    **要守的不是「取哪个」而是「响应与磁盘对得上」**：调用方按响应里的 path 去预览与
    下载，说的那个必须就是落盘的那个，否则它会对着一个不存在的路径打转。
    """
    response = client.post(
        f"/api/threads/{thread_id}/files",
        files=[
            ("file", ("one.csv", io.BytesIO(b"1"), "text/csv")),
            ("file", ("two.csv", io.BytesIO(b"2"), "text/csv")),
        ],
    )

    assert {one.name for one in space.path(thread_id).iterdir()} == {response.json()["path"]}


# ------------------------------------------------------------------ 上传大小上限
class TestUploadLimit:
    """把上限调到几个字节再验，免得为了这道闸造一个 64MB 的请求。

    **夹具的覆盖写在类里**：写成模块级的会把上面每一条上传用例也一起限到 8 字节。
    """

    @pytest.fixture
    def upload_max_byte(self) -> int:
        return 8

    def test_an_oversized_upload_is_refused(self, client: TestClient, thread_id: str) -> None:
        """直接跑 uvicorn 时没有 nginx，挡它的只有这一道。"""
        response = upload(client, thread_id, "big.csv", b"x" * 9)

        assert response.status_code == 413  # type: ignore[attr-defined]
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"  # type: ignore[attr-defined]

    def test_an_oversized_upload_writes_nothing(self, client: TestClient, thread_id: str, space: Workspace) -> None:
        """拦在读字节之前，否则内存已经吃掉了。"""
        upload(client, thread_id, "big.csv", b"x" * 9)

        assert not (space.path(thread_id) / "big.csv").exists()

    def test_an_upload_within_the_limit_still_goes_through(
        self, client: TestClient, thread_id: str, space: Workspace
    ) -> None:
        assert upload(client, thread_id, "small.csv", b"x" * 8).status_code == 201  # type: ignore[attr-defined]
        assert (space.path(thread_id) / "small.csv").exists()


# ------------------------------------------------------------------ 删除
def test_deleting_a_file_takes_it_off_disk(client: TestClient, thread_id: str, space: Workspace) -> None:
    make(space, thread_id, "holdings.csv", b"a,b\n")

    response = client.delete(f"/api/threads/{thread_id}/files", params={"path": "holdings.csv"})

    assert response.status_code == 204
    assert not (space.path(thread_id) / "holdings.csv").exists()


def test_a_deleted_file_leaves_the_tree(client: TestClient, thread_id: str, space: Workspace) -> None:
    make(space, thread_id, "holdings.csv", b"a,b\n")
    client.delete(f"/api/threads/{thread_id}/files", params={"path": "holdings.csv"})

    assert tree(client, thread_id).json()["entries"] == []  # type: ignore[attr-defined]


def test_deleting_a_directory_is_refused(client: TestClient, thread_id: str, space: Workspace) -> None:
    """删目录会连着里面的东西一起没，而侧边栏上那一下点击看不出这个后果。"""
    make(space, thread_id, "outputs/chart.png", b"png")

    response = client.delete(f"/api/threads/{thread_id}/files", params={"path": "outputs"})

    assert response.status_code == 422
    assert (space.path(thread_id) / "outputs" / "chart.png").exists()


def test_deleting_a_missing_file_is_not_found(client: TestClient, thread_id: str) -> None:
    response = client.delete(f"/api/threads/{thread_id}/files", params={"path": "never-made.csv"})

    assert response.status_code == 404


@pytest.mark.parametrize("path", ["../../etc/passwd", "/etc/passwd"])
def test_deleting_outside_the_workspace_is_refused(client: TestClient, thread_id: str, path: str) -> None:
    assert client.delete(f"/api/threads/{thread_id}/files", params={"path": path}).status_code == 404


def test_deleting_is_refused_while_reading_still_works(client: TestClient, thread_id: str, space: Workspace) -> None:
    """删除失败之后文件必须还在 —— 回答对了却把事情做了，比回答错更糟。"""
    make(space, thread_id, "outputs/chart.png", b"png")

    client.delete(f"/api/threads/{thread_id}/files", params={"path": "outputs"})

    assert client.get(f"/api/threads/{thread_id}/files/raw", params={"path": "outputs/chart.png"}).content == b"png"
