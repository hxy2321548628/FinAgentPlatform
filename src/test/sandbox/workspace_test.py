from pathlib import Path
from uuid import uuid4

import pytest

from app.sandbox.path import MEMORY_DIR, OUTPUT_DIR, PathEscapeError
from app.sandbox.quota import QuotaError
from app.sandbox.workspace import Workspace


@pytest.fixture
def space(tmp_path: Path) -> Workspace:
    return Workspace(root=tmp_path)


# ------------------------------------------------------------------ 会话
def test_a_new_thread_gets_a_directory(space: Workspace, tmp_path: Path) -> None:
    thread_id = space.create(uuid4().hex)

    assert (tmp_path / thread_id).is_dir()


def test_the_identifier_comes_from_the_caller(space: Workspace) -> None:
    """会话的身份长在 threads 表上，目录只是它的副产品 —— 这里不发号。"""
    thread_id = uuid4().hex

    assert space.create(thread_id) == thread_id


def test_a_created_thread_exists(space: Workspace) -> None:
    assert space.exists(space.create(uuid4().hex))


def test_an_unknown_thread_does_not_exist(space: Workspace) -> None:
    assert not space.exists("never-created")


@pytest.mark.parametrize("thread_id", ["../elsewhere", "a/b", "", "."])
def test_an_illegal_thread_id_reads_as_not_existing(space: Workspace, thread_id: str) -> None:
    """分成「不存在」和「格式不对」两种回答，等于告诉调用方哪些 id 是真的。"""
    assert not space.exists(thread_id)


def test_path_creates_the_directory_on_demand(space: Workspace, tmp_path: Path) -> None:
    workspace = space.path("thread-1")

    assert workspace == tmp_path / "thread-1"
    assert workspace.is_dir()


def test_path_rejects_a_thread_id_that_escapes_the_root(space: Workspace) -> None:
    with pytest.raises(PathEscapeError):
        space.path("../elsewhere")


def test_lookup_never_creates_an_unknown_thread(space: Workspace, tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        space.lookup("deleted-thread")

    assert not (tmp_path / "deleted-thread").exists()


def test_resolve_existing_never_creates_an_unknown_thread(space: Workspace, tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        space.resolve_existing("deleted-thread", "data.csv")

    assert not (tmp_path / "deleted-thread").exists()


# ------------------------------------------------------------------ 上传
def test_an_uploaded_file_lands_in_the_thread_directory(space: Workspace, tmp_path: Path) -> None:
    thread_id = space.create(uuid4().hex)

    saved = space.save(thread_id, "holdings.csv", b"a,b\n")

    assert saved == tmp_path / thread_id / "holdings.csv"
    assert saved.read_bytes() == b"a,b\n"


def test_the_agent_sees_an_uploaded_file_at_the_workspace_root(space: Workspace) -> None:
    """提示词告诉 agent 工作目录是 /workspace，上传的数据必须就在那一层。"""
    thread_id = space.create(uuid4().hex)

    saved = space.save(thread_id, "holdings.csv", b"x")

    assert saved.parent == space.path(thread_id)


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("../../etc/passwd", "passwd"),
        ("/etc/passwd", "passwd"),
        ("sub/dir/data.csv", "data.csv"),
    ],
)
def test_a_traversing_filename_is_reduced_to_its_last_segment(
    space: Workspace, tmp_path: Path, filename: str, expected: str
) -> None:
    """文件名来自 HTTP 请求，是不可信输入。"""
    thread_id = space.create(uuid4().hex)

    saved = space.save(thread_id, filename, b"x")

    assert saved == tmp_path / thread_id / expected


@pytest.mark.parametrize("filename", ["", "..", ".", "/", "../"])
def test_a_filename_with_no_usable_segment_is_rejected(space: Workspace, filename: str) -> None:
    thread_id = space.create(uuid4().hex)

    with pytest.raises(PathEscapeError):
        space.save(thread_id, filename, b"x")


def test_uploading_the_same_name_twice_overwrites(space: Workspace) -> None:
    thread_id = space.create(uuid4().hex)
    space.save(thread_id, "data.csv", b"old")

    saved = space.save(thread_id, "data.csv", b"new")

    assert saved.read_bytes() == b"new"


def test_a_file_can_be_uploaded_into_an_existing_subdirectory(space: Workspace) -> None:
    thread_id = space.create(uuid4().hex)
    (space.path(thread_id) / "data").mkdir()

    saved = space.save(thread_id, "holdings.csv", b"x", directory="data")

    assert saved == space.path(thread_id) / "data" / "holdings.csv"


def test_uploading_into_a_directory_that_is_not_there_is_rejected(space: Workspace) -> None:
    """目录来自侧边栏上的一次点击，点得到就说明它在 —— 不在就是请求本身不对。

    顺带躲开一个坑：broker 在容器里是 root，它建出来的目录沙箱一个字节都写不进去。
    """
    thread_id = space.create(uuid4().hex)

    with pytest.raises(PathEscapeError):
        space.save(thread_id, "holdings.csv", b"x", directory="never-made")


def test_uploading_into_a_file_instead_of_a_directory_is_rejected(space: Workspace) -> None:
    thread_id = space.create(uuid4().hex)
    space.save(thread_id, "data.csv", b"x")

    with pytest.raises(PathEscapeError):
        space.save(thread_id, "holdings.csv", b"x", directory="data.csv")


@pytest.mark.parametrize("directory", ["skill", "skill/nested", "data/../skill"])
def test_uploading_into_the_reserved_skill_directory_is_rejected(space: Workspace, directory: str) -> None:
    thread_id = space.create(uuid4().hex)
    (space.path(thread_id) / "skill" / "nested").mkdir(parents=True)

    with pytest.raises(PathEscapeError, match="保留目录"):
        space.save(thread_id, "holdings.csv", b"x", directory=directory)


@pytest.mark.parametrize("directory", ["..", "../elsewhere", "/etc"])
def test_an_upload_directory_that_escapes_the_workspace_is_rejected(space: Workspace, directory: str) -> None:
    thread_id = space.create(uuid4().hex)

    with pytest.raises(PathEscapeError):
        space.save(thread_id, "holdings.csv", b"x", directory=directory)


# ------------------------------------------------------------------ 定位与删除
def test_resolve_finds_a_file_anywhere_under_the_workspace(space: Workspace) -> None:
    thread_id = space.create(uuid4().hex)
    (space.path(thread_id) / OUTPUT_DIR).mkdir()
    (space.path(thread_id) / OUTPUT_DIR / "chart.png").write_bytes(b"png")

    assert space.resolve(thread_id, f"{OUTPUT_DIR}/chart.png").read_bytes() == b"png"


@pytest.mark.parametrize("relative", ["../holdings.csv", "../../etc/passwd", "/etc/passwd"])
def test_resolving_a_path_that_escapes_the_workspace_is_rejected(space: Workspace, relative: str) -> None:
    """不挡住的话，文件浏览就成了任意文件读取。"""
    thread_id = space.create(uuid4().hex)

    with pytest.raises(PathEscapeError):
        space.resolve(thread_id, relative)


def test_resolving_a_symlink_pointing_outside_is_rejected(space: Workspace, tmp_path: Path) -> None:
    thread_id = space.create(uuid4().hex)
    secret = tmp_path / "secret.txt"
    secret.write_text("凭据", encoding="utf-8")
    (space.path(thread_id) / "link.txt").symlink_to(secret)

    with pytest.raises(PathEscapeError):
        space.resolve(thread_id, "link.txt")


def test_removing_a_file_takes_it_off_disk(space: Workspace) -> None:
    thread_id = space.create(uuid4().hex)
    space.save(thread_id, "data.csv", b"x")

    space.remove(thread_id, "data.csv")

    assert not (space.path(thread_id) / "data.csv").exists()


def test_removing_a_file_that_is_not_there_is_rejected(space: Workspace) -> None:
    thread_id = space.create(uuid4().hex)

    with pytest.raises(FileNotFoundError):
        space.remove(thread_id, "never-made.csv")


def test_removing_a_directory_is_rejected(space: Workspace) -> None:
    """删目录会连着里面的东西一起没，而侧边栏上那一下点击看不出这个后果。"""
    thread_id = space.create(uuid4().hex)
    (space.path(thread_id) / OUTPUT_DIR).mkdir()

    with pytest.raises(IsADirectoryError):
        space.remove(thread_id, OUTPUT_DIR)


@pytest.mark.parametrize("relative", ["../holdings.csv", "/etc/passwd"])
def test_removing_a_path_that_escapes_the_workspace_is_rejected(space: Workspace, relative: str) -> None:
    thread_id = space.create(uuid4().hex)

    with pytest.raises(PathEscapeError):
        space.remove(thread_id, relative)


# ------------------------------------------------------------------ 磁盘配额
class SpyQuota:
    """记下被要求给哪些目录设配额。"""

    def __init__(self) -> None:
        self.assigned: list[tuple[str, Path]] = []
        self.fail_with: Exception | None = None

    def assign(self, thread_id: str, workspace: Path) -> None:
        if self.fail_with is not None:
            raise self.fail_with
        self.assigned.append((thread_id, workspace))


def test_a_new_thread_gets_its_quota(tmp_path: Path) -> None:
    quota = SpyQuota()
    space = Workspace(root=tmp_path, quota=quota)

    thread_id = space.create(uuid4().hex)

    assert quota.assigned == [(thread_id, tmp_path / thread_id)]


def test_quota_is_set_once_and_not_on_every_lookup(tmp_path: Path) -> None:
    """XFS 配额落在盘上，重设一遍不会更安全，只会给每次 read_file 搭上两个子进程。"""
    quota = SpyQuota()
    space = Workspace(root=tmp_path, quota=quota)

    space.path("thread-1")
    space.path("thread-1")

    assert len(quota.assigned) == 1


def test_a_failing_quota_stops_the_thread_from_being_used(tmp_path: Path) -> None:
    """设不上配额就是缺口敞着，不能当没事发生继续往下走。"""
    quota = SpyQuota()
    quota.fail_with = QuotaError("xfs_quota 没权限")
    space = Workspace(root=tmp_path, quota=quota)

    with pytest.raises(QuotaError):
        space.path("thread-1")


def test_without_a_quota_the_directory_still_works(tmp_path: Path) -> None:
    """CI 与没挂 XFS 的开发机上平台仍要能跑起来。"""
    space = Workspace(root=tmp_path)

    assert space.path("thread-1").is_dir()


def test_a_new_directory_is_handed_to_the_sandbox_user(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Broker 在容器里是 root，不改属主的话沙箱（以宿主用户跑）写不进去。

    症状极具迷惑性：execute 照常成功、没有一条报错指向权限，只是产物一个都没有。
    """
    handed: list[tuple[Path, int, int]] = []
    monkeypatch.setattr("app.sandbox.workspace.os.chown", lambda path, uid, gid: handed.append((path, uid, gid)))
    space = Workspace(root=tmp_path, owner=(1000, 1000))

    thread_id = space.create(uuid4().hex)

    assert handed == [(tmp_path / thread_id, 1000, 1000)]


def test_without_an_owner_the_directory_is_left_alone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """直接跑 uvicorn 时进程本就是宿主用户，不该多此一举地 chown。"""
    handed: list[object] = []
    monkeypatch.setattr("app.sandbox.workspace.os.chown", lambda *argument: handed.append(argument))
    space = Workspace(root=tmp_path)

    space.create(uuid4().hex)

    assert handed == []


# ------------------------------------------------------------------ 删会话
def test_destroy_removes_the_whole_thread_directory(space: Workspace) -> None:
    """删会话是唯一递归删除的操作 —— 教师点的那一下就是「整个会话都不要了」。"""
    thread_id = space.create(uuid4().hex)
    space.save(thread_id, "data.csv", b"a,b")
    (space.path(thread_id) / OUTPUT_DIR).mkdir(exist_ok=True)

    space.destroy(thread_id)

    assert space.exists(thread_id) is False


def test_destroying_a_thread_twice_is_not_an_error(space: Workspace) -> None:
    """Api 那边的行已经没了，这里再报错只会让一次正常的删除看起来失败了。"""
    thread_id = space.create(uuid4().hex)
    space.destroy(thread_id)

    space.destroy(thread_id)


def test_destroying_a_thread_leaves_the_others_alone(space: Workspace) -> None:
    mine, theirs = uuid4().hex, uuid4().hex
    space.create(mine)
    space.create(theirs)
    space.save(mine, "mine.csv", b"a")
    space.save(theirs, "theirs.csv", b"b")

    space.destroy(mine)

    assert space.exists(theirs) is True


def test_destroying_an_escaping_identifier_is_refused(space: Workspace) -> None:
    """标识参与拼路径。这一条要是漏了，`../..` 就是一条递归删宿主机目录的路。"""
    with pytest.raises(PathEscapeError):
        space.destroy("../../etc")


# ------------------------------------------------------------------ 侧边栏编辑与创建
def test_a_workspace_file_can_be_overwritten(space: Workspace) -> None:
    thread_id = space.create(uuid4().hex)
    space.save(thread_id, "analysis.py", b"old")

    saved = space.write(thread_id, "analysis.py", b"new")

    assert saved.read_bytes() == b"new"


def test_writing_requires_an_existing_parent_directory(space: Workspace) -> None:
    thread_id = space.create(uuid4().hex)

    with pytest.raises(PathEscapeError):
        space.write(thread_id, "missing/analysis.py", b"x")


def test_a_workspace_directory_can_be_created(space: Workspace) -> None:
    thread_id = space.create(uuid4().hex)

    created = space.mkdir(thread_id, "analysis")

    assert created.is_dir()


def test_directory_creation_requires_an_existing_parent(space: Workspace) -> None:
    thread_id = space.create(uuid4().hex)

    with pytest.raises(PathEscapeError):
        space.mkdir(thread_id, "missing/analysis")


def test_workspace_editing_cannot_touch_reserved_skill_directory(space: Workspace) -> None:
    thread_id = space.create(uuid4().hex)
    (space.path(thread_id) / "skill").mkdir()

    with pytest.raises(PathEscapeError):
        space.write(thread_id, "skill/config.toml", b"x")


@pytest.mark.parametrize(
    ("operation", "relative_path"),
    [
        ("write", f"{MEMORY_DIR}/record.md"),
        ("mkdir", MEMORY_DIR),
        ("remove", f"{MEMORY_DIR}/record.md"),
        ("resolve", f"data/../{MEMORY_DIR}/record.md"),
    ],
)
def test_ordinary_workspace_operations_cannot_touch_memory(
    space: Workspace, operation: str, relative_path: str
) -> None:
    thread_id = space.create(uuid4().hex)
    memory = space.lookup(thread_id) / MEMORY_DIR
    memory.mkdir()
    (memory / "record.md").write_text("记忆", encoding="utf-8")

    with pytest.raises(PathEscapeError, match="保留目录"):
        if operation == "write":
            space.write(thread_id, relative_path, b"x")
        elif operation == "mkdir":
            space.mkdir(thread_id, relative_path)
        elif operation == "remove":
            space.remove(thread_id, relative_path)
        else:
            space.resolve(thread_id, relative_path)


def test_uploading_into_memory_is_rejected(space: Workspace) -> None:
    thread_id = space.create(uuid4().hex)
    (space.lookup(thread_id) / MEMORY_DIR).mkdir()

    with pytest.raises(PathEscapeError, match="保留目录"):
        space.save(thread_id, "record.md", b"x", directory=MEMORY_DIR)


def test_uploading_a_file_named_memory_cannot_claim_the_reserved_path(space: Workspace) -> None:
    thread_id = space.create(uuid4().hex)

    with pytest.raises(PathEscapeError, match="保留目录"):
        space.save(thread_id, MEMORY_DIR, b"x")

    assert not (space.lookup(thread_id) / MEMORY_DIR).exists()
