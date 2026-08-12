"""三道闸在端点上的测试：各触发一次，三个 `code` 都要出现过。

**只给 HTTP 429 是不够的**：三者的前端行为完全不同 —— 频率限制该自动退避重试，
配额耗尽该提示明天再来，并发超限该提示先等已有任务跑完。因此这个文件断言的是
`code`，不是状态码。

**token 那道闸用「预置用量」触发，不靠真烧**：把当日已用量直接写到上限之上再提交
一次。烧满一个真实日配额又慢又贵，而这里要验的是闸门与扣减口径，不是模型。

调档的办法是**把运行时换掉**（`Platform` 是冻结的 dataclass，`replace` 出一个新的
挂回 `app.state`）—— 端点每次请求都从那里取，因此换完立刻生效，而且不必为了一条
用例再起一个应用。
"""

from dataclasses import replace
from functools import partial
from uuid import uuid4

from fastapi.testclient import TestClient
from redis.asyncio import Redis

from api.platform import Platform
from auth.password import PasswordHasher
from event.model import TokenUsage
from quota.policy import QuotaPolicy
from quota.rate import RateLimiter
from test.api.conftest import TEST_RATE_WINDOW_SECOND, signup
from user.model import UserRole

# 一次「预置用量」的大小。取一个明显超过任何角色档位的数，
# 免得将来改档位时这个文件要跟着一起改
PRESET_TOKEN = 10_000_000


def _swap(client: TestClient, **change: object) -> None:
    """把运行时换成改过某几项的版本。"""
    client.app.state.platform = replace(client.app.state.platform, **change)  # type: ignore[attr-defined]


def _tighten_rate(client: TestClient, live_cache: Redis, *, limit: int) -> None:
    _swap(client, rate=RateLimiter(live_cache, limit=limit, window_second=TEST_RATE_WINDOW_SECOND))


def _tighten_concurrency(client: TestClient, *, limit: int) -> None:
    _swap(client, policy=QuotaPolicy(concurrent_run=dict.fromkeys(UserRole, limit)))


def _relax_concurrency(client: TestClient) -> None:
    _swap(client, policy=QuotaPolicy())


async def _preset(platform: Platform, user_id: str, thread_id: str, tokens: TokenUsage) -> None:
    """给这个用户记一次已经跑完的 run，用量直接写进去。"""
    run_id = uuid4().hex
    await platform.repository.create(run_id=run_id, thread_id=thread_id, user_id=user_id)
    await platform.repository.succeed(run_id, tokens=tokens)


def _burn(client: TestClient, platform: Platform, thread_id: str, tokens: TokenUsage) -> None:
    assert client.portal is not None
    identity = client.get("/api/auth/me").json()["id"]
    client.portal.call(partial(_preset, platform, identity, thread_id, tokens))


def _submit(client: TestClient, thread_id: str) -> dict[str, object]:
    body: dict[str, object] = client.post(f"/api/threads/{thread_id}/runs", json={"content": "再来一次"}).json()
    return body


def test_token_quota_exhausted_reports_its_own_code(client: TestClient, platform: Platform, thread_id: str) -> None:
    _burn(client, platform, thread_id, TokenUsage(input_uncached=PRESET_TOKEN))

    response = client.post(f"/api/threads/{thread_id}/runs", json={"content": "再来一次"})

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "QUOTA_EXCEEDED"


def test_the_quota_message_says_when_it_resets(client: TestClient, platform: Platform, thread_id: str) -> None:
    """「明日 0 点重置」这句话要与真正的重置时刻对得上，否则教师会白来一趟。"""
    _burn(client, platform, thread_id, TokenUsage(input_uncached=PRESET_TOKEN))

    error = _submit(client, thread_id)["error"]
    assert isinstance(error, dict)

    assert "重置" in str(error["message"])


def test_cache_hits_do_not_push_a_user_over_the_quota(client: TestClient, platform: Platform, thread_id: str) -> None:
    """同样大的 input 总数，命中的那份不该把人挤出去。

    这是验证②在端点上的形态：按 input 总数扣的话这一次早就超了，
    按未命中扣则连一个零头都没用掉。
    """
    _burn(client, platform, thread_id, TokenUsage(input_cache_read=PRESET_TOKEN, input_uncached=10, output=5))

    response = client.post(f"/api/threads/{thread_id}/runs", json={"content": "还该放行"})

    assert response.status_code == 202


def test_concurrency_limit_reports_its_own_code(client: TestClient, thread_id: str) -> None:
    _tighten_concurrency(client, limit=0)

    response = client.post(f"/api/threads/{thread_id}/runs", json={"content": "再来一次"})

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "CONCURRENCY_LIMIT"


def test_a_queued_run_counts_against_the_concurrency_limit(
    client: TestClient, platform: Platform, thread_id: str
) -> None:
    """上限 1 时，手里已经有一条没跑完的 run，下一次提交就该被拦住。

    **那条 run 直接写库，不投队列**：同进程里跑着一个 worker，走队列的话它转眼就跑完了，
    这条用例的真假会取决于两次请求之间的快慢。
    """
    assert client.portal is not None
    identity = client.get("/api/auth/me").json()["id"]
    client.portal.call(partial(platform.repository.create, run_id=uuid4().hex, thread_id=thread_id, user_id=identity))
    _tighten_concurrency(client, limit=1)

    response = client.post(f"/api/threads/{thread_id}/runs", json={"content": "二"})

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "CONCURRENCY_LIMIT"


def test_rate_limit_reports_its_own_code(client: TestClient, live_cache: Redis) -> None:
    """打的是业务端点，而且是一个根本不存在的 run。

    **限流挂在路由器上**，依赖在端点之前跑 —— 洪水本来就该在查库之前被挡下来。
    """
    _tighten_rate(client, live_cache, limit=1)

    client.get(f"/api/runs/{uuid4().hex}")
    response = client.get(f"/api/runs/{uuid4().hex}")

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_LIMITED"


def test_login_is_rate_limited_too(
    client: TestClient, platform: Platform, hasher: PasswordHasher, live_cache: Redis
) -> None:
    """登录是唯一未认证还能打的业务端口。不限它等于把口令爆破的门开着。"""
    name = f"teacher-{uuid4().hex[:8]}"
    signup(client, platform, hasher, name=name)
    _tighten_rate(client, live_cache, limit=1)

    client.post("/api/auth/login", json={"name": name, "password": "错的"})
    response = client.post("/api/auth/login", json={"name": name, "password": "错的"})

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_LIMITED"


def test_the_three_gates_use_three_different_codes(
    client: TestClient, platform: Platform, live_cache: Redis, thread_id: str
) -> None:
    """三个 code 各自出现过才算通过 —— 只给 429 的话前端分不出该做哪一件事。"""
    _tighten_concurrency(client, limit=0)
    seen = {_code(_submit(client, thread_id))}

    _relax_concurrency(client)
    _burn(client, platform, thread_id, TokenUsage(input_uncached=PRESET_TOKEN))
    seen.add(_code(_submit(client, thread_id)))

    _tighten_rate(client, live_cache, limit=1)
    client.get(f"/api/runs/{uuid4().hex}")
    seen.add(_code(client.get(f"/api/runs/{uuid4().hex}").json()))

    assert seen == {"CONCURRENCY_LIMIT", "QUOTA_EXCEEDED", "RATE_LIMITED"}


def _code(body: dict[str, object]) -> str:
    error = body["error"]
    assert isinstance(error, dict)
    return str(error["code"])
