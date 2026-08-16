"""审核记录读写的测试，连真 Postgres。"""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from preset.model import ResourceKind, ReviewStatus
from preset.repository import AgentRepository
from preset.review import ReviewRepository, _item_select
from test.conftest import FAKE_HASH
from user.model import UserRole
from user.repository import User, UserRepository


@pytest.fixture
def agents(live_engine: AsyncEngine) -> AgentRepository:
    return AgentRepository(live_engine)


@pytest.fixture
def reviews(live_engine: AsyncEngine) -> ReviewRepository:
    return ReviewRepository(live_engine)


@pytest.fixture
def users(live_engine: AsyncEngine) -> UserRepository:
    return UserRepository(live_engine)


async def _reviewer(users: UserRepository) -> User:
    return await users.create(
        name=f"reviewer-{uuid4().hex[:8]}",
        email=f"{uuid4().hex[:8]}@zuel.edu.cn",
        password_hash=FAKE_HASH,
        role=UserRole.REVIEWER,
    )


async def _released_version(agents: AgentRepository, owner: User, *, prompt: str = "每一句都以喵开头") -> str:
    created = await agents.create(
        owner_id=owner.id,
        name=f"喵语老师-{uuid4().hex[:8]}",
        description="说话带喵",
        subject="金融学",
        system_prompt=prompt,
    )
    assert created is not None
    released = await agents.release(created.id, owner_id=owner.id)
    assert released is not None
    return released.id


async def test_a_submitted_review_waits_for_a_decision(
    agents: AgentRepository, reviews: ReviewRepository, owner: User
) -> None:
    version_id = await _released_version(agents, owner)

    submitted = await reviews.submit(target_id=version_id, submitted_by=owner.id, responsibility_confirmed=True)

    assert submitted is not None
    assert submitted.status is ReviewStatus.PENDING
    assert submitted.responsibility_confirmed is True
    assert submitted.id in {one.review.id for one in await reviews.list_pending()}


async def test_submitting_twice_leaves_one_item_in_the_queue(
    agents: AgentRepository, reviews: ReviewRepository, owner: User
) -> None:
    """连点两次提审只该在 reviewer 的队列里留下一条。"""
    version_id = await _released_version(agents, owner)
    await reviews.submit(target_id=version_id, submitted_by=owner.id, responsibility_confirmed=True)

    again = await reviews.submit(target_id=version_id, submitted_by=owner.id, responsibility_confirmed=True)

    assert again is None
    assert len(await reviews.list_for_target([version_id])) == 1


async def test_the_queue_carries_what_a_reviewer_needs_to_judge(
    agents: AgentRepository, reviews: ReviewRepository, owner: User
) -> None:
    """提示词全文在队列行里 —— 让 reviewer 再点一次去别处取，等于把审核变成走过场。"""
    version_id = await _released_version(agents, owner, prompt="每一句都以喵开头")
    await reviews.submit(target_id=version_id, submitted_by=owner.id, responsibility_confirmed=True)

    queued = [one for one in await reviews.list_pending() if one.review.target_id == version_id]

    assert len(queued) == 1
    assert queued[0].system_prompt == "每一句都以喵开头"
    assert queued[0].owner_name == owner.name
    assert queued[0].version == 1


async def test_rejecting_keeps_the_reason_word_for_word(
    agents: AgentRepository, reviews: ReviewRepository, users: UserRepository, owner: User
) -> None:
    reviewer = await _reviewer(users)
    version_id = await _released_version(agents, owner)
    submitted = await reviews.submit(target_id=version_id, submitted_by=owner.id, responsibility_confirmed=True)
    assert submitted is not None

    decided = await reviews.decide(submitted.id, reviewer_id=reviewer.id, approved=False, reason="提示词过于宽泛")

    assert decided is True
    found = await reviews.get(submitted.id)
    assert found is not None
    assert found.status is ReviewStatus.REJECTED
    assert found.reason == "提示词过于宽泛"
    assert found.reviewed_by == reviewer.id
    assert submitted.id not in {one.review.id for one in await reviews.list_pending()}


async def test_a_second_decision_changes_nothing(
    agents: AgentRepository, reviews: ReviewRepository, users: UserRepository, owner: User
) -> None:
    """两个 reviewer 各点一次时，「先读再写」的那一份会把拒绝改成通过。"""
    reviewer = await _reviewer(users)
    version_id = await _released_version(agents, owner)
    submitted = await reviews.submit(target_id=version_id, submitted_by=owner.id, responsibility_confirmed=True)
    assert submitted is not None
    await reviews.decide(submitted.id, reviewer_id=reviewer.id, approved=False, reason="不行")

    again = await reviews.decide(submitted.id, reviewer_id=reviewer.id, approved=True, reason=None)

    assert again is False
    found = await reviews.get(submitted.id)
    assert found is not None
    assert found.status is ReviewStatus.REJECTED


async def test_a_rejected_version_can_be_submitted_again(
    agents: AgentRepository, reviews: ReviewRepository, users: UserRepository, owner: User
) -> None:
    reviewer = await _reviewer(users)
    version_id = await _released_version(agents, owner)
    first = await reviews.submit(target_id=version_id, submitted_by=owner.id, responsibility_confirmed=True)
    assert first is not None
    await reviews.decide(first.id, reviewer_id=reviewer.id, approved=False, reason="改一下")

    second = await reviews.submit(target_id=version_id, submitted_by=owner.id, responsibility_confirmed=True)

    assert second is not None
    assert len(await reviews.list_for_target([version_id])) == 2


async def test_decided_items_are_still_findable(
    agents: AgentRepository, reviews: ReviewRepository, users: UserRepository, owner: User
) -> None:
    """队列清空之后打开这一页看到的不该是一片空白 —— 「我刚才审的那条呢」必然会问。"""
    reviewer = await _reviewer(users)
    version_id = await _released_version(agents, owner)
    submitted = await reviews.submit(target_id=version_id, submitted_by=owner.id, responsibility_confirmed=True)
    assert submitted is not None
    await reviews.decide(submitted.id, reviewer_id=reviewer.id, approved=True, reason=None)

    assert submitted.id in {one.review.id for one in await reviews.list_decided(limit=50)}


async def test_asking_for_no_targets_queries_nothing(reviews: ReviewRepository) -> None:
    """空列表要在这一层短路：`IN ()` 在 Postgres 上是语法错误。"""
    assert await reviews.list_for_target([]) == []
    assert await reviews.list_for_target(["不是-uuid"]) == []


async def test_a_malformed_identifier_is_a_miss_not_a_crash(reviews: ReviewRepository, owner: User) -> None:
    assert await reviews.get("不是-uuid") is None
    assert await reviews.submit(target_id="不是-uuid", submitted_by=owner.id, responsibility_confirmed=True) is None
    assert await reviews.decide("不是-uuid", reviewer_id=owner.id, approved=True, reason=None) is False


async def test_an_mcp_review_does_not_duplicate_the_skill_queue(
    agents: AgentRepository, reviews: ReviewRepository, owner: User
) -> None:
    """P10 §6 第 5 条：加进 `ResourceKind.MCP` 之后队列里每条记录仍只出现一次。

    原来的 `_item_select` 是「AGENT 走一支、其余都走 skill 那一支」，`_for_status`
    则 `for kind in ResourceKind` 逐个拼查询 —— 多一个 kind 就把 skill 的待审记录
    查两遍，第二遍还标成 MCP。**这个错不报任何异常**，症状只是审核队列里每条申请
    出现两次。
    """
    version_id = await _released_version(agents, owner)
    submitted = await reviews.submit(target_id=version_id, submitted_by=owner.id, responsibility_confirmed=True)
    assert submitted is not None
    mcp = await reviews.submit(
        target_id=uuid4().hex,
        submitted_by=owner.id,
        responsibility_confirmed=True,
        target_kind=ResourceKind.MCP,
    )
    assert mcp is not None

    queue = await reviews.list_pending()

    identifiers = [one.review.id for one in queue]
    assert identifiers.count(submitted.id) == 1
    # MCP 的审批是安全边界决定，只有管理员能做 —— 它不进 reviewer 的队列
    assert mcp.id not in identifiers
    assert all(one.review.target_kind is not ResourceKind.MCP for one in queue)


def test_the_reviewer_queue_refuses_to_guess_at_an_unhandled_kind() -> None:
    """缺一种 kind 就抛，不留兜底的 else —— 兜底的那一支正是上一条测的那个 bug。"""
    with pytest.raises(ValueError, match="MCP"):
        _item_select(ResourceKind.MCP)
