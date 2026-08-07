"""写操作去重在端点上的测试：同一个键重放时不进沙箱，纯读工具不受影响。

**用真 broker 路由 + 真 Redis**，只把沙箱换成会数次数的替身 —— 要验的正是
「第二次调用没有落到沙箱上」，而那件事只有数次数才看得见。
"""

from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from redis.asyncio import Redis

from broker.app import create_app
from broker.cache import ToolCache
from broker.runtime import Broker
from sandbox.container import CommandResult
from sandbox.workspace import Workspace

THREAD = "thread-dedupe"

NS = "tools:fd422cb9-d8b8-c0ae-510d-64ed2e099a1c"

BROKER_URL = "http://broker.test"


class CountingContainer:
    """会数「进了几次沙箱」的假容器。"""

    def __init__(self) -> None:
        self.executed: list[str] = []

    @property
    def id(self) -> str:
        return "counting"

    def exec(self, command: str, *, timeout: int) -> CommandResult:
        self.executed.append(command)
        return CommandResult(output=f"第 {len(self.executed)} 次", exit_code=0)


class CountingPool:
    def __init__(self, container: CountingContainer) -> None:
        self._container = container

    def current(self, thread_id: str) -> CountingContainer:
        return self._container


@pytest.fixture
def container() -> CountingContainer:
    return CountingContainer()


@pytest.fixture
def space(tmp_path: Path) -> Workspace:
    created = Workspace(root=tmp_path)
    created.create(THREAD)
    return created


@pytest.fixture
def client(space: Workspace, container: CountingContainer, live_cache: Redis) -> httpx.AsyncClient:
    broker = Broker(workspace=space, pool=CountingPool(container), cache=ToolCache(live_cache))  # type: ignore[arg-type]
    app = create_app(broker)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BROKER_URL)


async def _call(client: httpx.AsyncClient, tool: str, payload: dict[str, object]) -> dict[str, object]:
    response = await client.post(f"/threads/{THREAD}/tool/{tool}", json=payload)
    response.raise_for_status()
    parsed: dict[str, object] = response.json()
    return parsed


async def test_a_replayed_execute_does_not_reach_the_sandbox(
    client: httpx.AsyncClient, container: CountingContainer
) -> None:
    """步骤六验证②：命中缓存时不进沙箱 —— 数的就是容器里跑了几次。"""
    payload: dict[str, object] = {"command": "echo 一", "checkpoint_ns": NS}

    first = await _call(client, "execute", payload)
    second = await _call(client, "execute", payload)

    assert container.executed == ["echo 一"]
    assert first == second


async def test_a_different_call_still_reaches_the_sandbox(
    client: httpx.AsyncClient, container: CountingContainer
) -> None:
    """去重不能把同一轮里的另一个调用也挡住 —— 它们的 ns 不同。"""
    await _call(client, "execute", {"command": "echo 一", "checkpoint_ns": NS})
    await _call(client, "execute", {"command": "echo 二", "checkpoint_ns": "tools:3ad455cb"})

    assert container.executed == ["echo 一", "echo 二"]


async def test_a_call_without_a_key_is_never_deduplicated(
    client: httpx.AsyncClient, container: CountingContainer
) -> None:
    """图之外调用时拿不到 ns。少一层去重只是回到没有它的从前，不该报错。"""
    await _call(client, "execute", {"command": "echo 一"})
    await _call(client, "execute", {"command": "echo 一"})

    assert len(container.executed) == 2


async def test_a_replayed_delete_returns_the_first_result_not_an_error(
    client: httpx.AsyncClient, space: Workspace
) -> None:
    """**这是幂等键真正要解决的那一幕。**

    首次删除成功；重放时文件已经没了，真去执行会返回一个首次执行时没有的错误，
    而 LLM 会据此改变后续行为。命中缓存则原样还回第一次的结果。
    """
    (space.path(THREAD) / "old.csv").write_text("a,b\n", encoding="utf-8")
    payload: dict[str, object] = {"file_path": "/workspace/old.csv", "checkpoint_ns": NS}

    first = await _call(client, "delete", payload)
    second = await _call(client, "delete", payload)

    assert first["error"] is None
    assert second == first


async def test_a_replayed_edit_returns_the_first_result_not_an_error(
    client: httpx.AsyncClient, space: Workspace
) -> None:
    """同上：重放时 `old_string` 已经被换掉了，真去执行会报「找不到」。"""
    (space.path(THREAD) / "note.txt").write_text("旧的", encoding="utf-8")
    payload: dict[str, object] = {
        "file_path": "/workspace/note.txt",
        "old_string": "旧的",
        "new_string": "新的",
        "checkpoint_ns": NS,
    }

    first = await _call(client, "edit", payload)
    second = await _call(client, "edit", payload)

    assert first["error"] is None
    assert second == first


async def test_a_replayed_write_returns_the_first_result(client: httpx.AsyncClient) -> None:
    payload: dict[str, object] = {"file_path": "/workspace/a.txt", "content": "一", "checkpoint_ns": NS}

    first = await _call(client, "write", payload)
    second = await _call(client, "write", payload)

    assert second == first


@pytest.mark.parametrize(
    ("tool", "payload"),
    [
        ("ls", {"path": "/workspace"}),
        ("read", {"file_path": "/workspace/read.txt"}),
        ("glob", {"pattern": "*.txt"}),
        ("grep", {"pattern": "内容"}),
    ],
)
async def test_read_only_tools_are_not_deduplicated(
    client: httpx.AsyncClient, space: Workspace, tool: str, payload: dict[str, object]
) -> None:
    """步骤六验证③：纯读工具不去重。

    它们没有副作用，重放一次得到的就是当时该得到的东西；缓存反而会把
    「文件后来变了」这件事藏起来。
    """
    target = space.path(THREAD) / "read.txt"
    target.write_text("内容一", encoding="utf-8")
    keyed = payload | {"checkpoint_ns": NS}

    await _call(client, tool, keyed)
    target.write_text("内容二", encoding="utf-8")
    after = await _call(client, tool, keyed)

    assert "内容一" not in str(after)


async def test_a_broker_without_a_cache_still_works(space: Workspace, container: CountingContainer) -> None:
    """没配 Redis 时去重整个关掉 —— 那只是回到没有它的从前，不该让 broker 起不来。"""
    app = create_app(Broker(workspace=space, pool=CountingPool(container)))  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BROKER_URL) as bare:
        await _call(bare, "execute", {"command": "echo 一", "checkpoint_ns": NS})
        await _call(bare, "execute", {"command": "echo 一", "checkpoint_ns": NS})

    assert len(container.executed) == 2


async def test_the_thread_is_part_of_the_key(client: httpx.AsyncClient, container: CountingContainer) -> None:
    """两个会话的 ns 撞上了也不能互相看见对方的结果。"""
    await _call(client, "execute", {"command": "echo 一", "checkpoint_ns": NS})

    response = await client.post(
        f"/threads/{uuid4().hex}/tool/execute", json={"command": "echo 一", "checkpoint_ns": NS}
    )
    response.raise_for_status()

    assert len(container.executed) == 2


async def test_a_reply_lost_after_execution_does_not_re_execute(
    client: httpx.AsyncClient, container: CountingContainer
) -> None:
    """**定点注入的那一刀**：沙箱已经跑完、结果也已记下，回程的响应丢了。

    worker 被 kill -9 之后由另一个副本重放同一次调用 —— 这一次必须命中缓存，
    否则那段代码就跑了两遍（LLM 生成的代码可能追加写、累加计数、删文件）。

    **残留风险按 ADR-0014 登记在案**：若崩溃发生在沙箱**执行途中**（结果还没记下），
    这条缓存里什么都没有，重放仍会真跑一次。那需要额外记一个 `started` 标记才认得出来，
    本期不做。
    """
    payload: dict[str, object] = {"command": "echo 累加", "checkpoint_ns": NS}
    await _call(client, "execute", payload)

    # worker 那一侧从此什么都没收到 —— 重放的是同一个 (thread_id, checkpoint_ns)
    replayed = await _call(client, "execute", payload)

    assert container.executed == ["echo 累加"]
    assert replayed["output"] == "第 1 次"
