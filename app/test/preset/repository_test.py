"""智能体目录读写的测试，连真 Postgres。

**越权那几条是这个文件的重点**，不是「查得到自己的」那几条。本期唯一会安静失效的
缺陷是「多看见了一条」—— 别组的老师在列表里刷到一个不该看到的 agent，既不报错也
不会有人来报。因此每一条可见性断言都是**双向**的：该看见的看得见，该看不见的看不见。
"""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from agent.config import SkillReference, SubagentReference
from group.repository import Group, GroupRepository
from preset.model import Visibility
from preset.repository import AgentRepository, AgentSource
from preset.review import ReviewRepository
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
def groups(live_engine: AsyncEngine) -> GroupRepository:
    return GroupRepository(live_engine)


@pytest.fixture
def users(live_engine: AsyncEngine) -> UserRepository:
    return UserRepository(live_engine)


async def _teacher(users: UserRepository) -> User:
    return await users.create(name=f"teacher-{uuid4().hex[:8]}", password_hash=FAKE_HASH, role=UserRole.TEACHER)


async def _agent_of(agents: AgentRepository, owner: User, *, prompt: str = "每一句都以喵开头") -> str:
    created = await agents.create(
        owner_id=owner.id,
        name=f"喵语老师-{uuid4().hex[:8]}",
        description="说话带喵",
        subject="金融学",
        system_prompt=prompt,
    )
    assert created is not None
    return created.id


async def _released(agents: AgentRepository, owner: User, *, prompt: str = "每一句都以喵开头") -> str:
    agent_id = await _agent_of(agents, owner, prompt=prompt)
    assert await agents.release(agent_id, owner_id=owner.id) is not None
    return agent_id


async def _shared_group(groups: GroupRepository, owner: User, member: User) -> Group:
    group = await groups.create(name=f"课题组-{uuid4().hex[:8]}", owner_id=owner.id)
    assert await groups.add_member(group_id=group.id, user_id=member.id) is True
    return group


async def _approve(reviews: ReviewRepository, version_id: str, author: User, reviewer: User) -> None:
    submitted = await reviews.submit(target_id=version_id, submitted_by=author.id, responsibility_confirmed=True)
    assert submitted is not None
    assert await reviews.decide(submitted.id, reviewer_id=reviewer.id, approved=True, reason=None) is True


async def test_a_new_agent_comes_with_its_first_draft(agents: AgentRepository, owner: User) -> None:
    """没有「只有身份没有内容」的中间态 —— 那样的行每个查询都要额外挡一次。"""
    agent_id = await _agent_of(agents, owner)

    detail = await agents.detail(agent_id, owner_id=owner.id)

    assert detail is not None
    assert [(one.version, one.status.value) for one in detail.versions] == [(1, "draft")]
    assert detail.agent.visibility is Visibility.PRIVATE


async def test_the_same_author_cannot_reuse_one_name(agents: AgentRepository, owner: User) -> None:
    name = f"重名-{uuid4().hex[:8]}"
    first = await agents.create(owner_id=owner.id, name=name, description="", subject="", system_prompt="x")

    again = await agents.create(owner_id=owner.id, name=name, description="", subject="", system_prompt="y")

    assert first is not None
    assert again is None


async def test_two_authors_may_use_the_same_name(agents: AgentRepository, users: UserRepository, owner: User) -> None:
    """全库唯一意味着谁先占了名字别人就不能用，而广场卡片本来就带作者名。"""
    other = await _teacher(users)
    name = f"波动率助手-{uuid4().hex[:8]}"

    mine = await agents.create(owner_id=owner.id, name=name, description="", subject="", system_prompt="x")
    theirs = await agents.create(owner_id=other.id, name=name, description="", subject="", system_prompt="x")

    assert mine is not None
    assert theirs is not None


async def test_releasing_freezes_the_draft_and_editing_appends_a_new_one(agents: AgentRepository, owner: User) -> None:
    """「再改 = 追加下一个版本号的新草稿」那条状态转移。"""
    agent_id = await _agent_of(agents, owner, prompt="喵")

    released = await agents.release(agent_id, owner_id=owner.id)
    appended = await agents.write_draft(agent_id, owner_id=owner.id, system_prompt="汪")

    assert released is not None
    assert (released.version, released.system_prompt) == (1, "喵")
    assert appended is not None
    assert (appended.version, appended.status.value) == (2, "draft")
    detail = await agents.detail(agent_id, owner_id=owner.id)
    assert detail is not None
    # v1 那一行一个字都没动 —— 落进 run 快照的引用要照常读得回来
    assert [(one.version, one.system_prompt) for one in detail.versions] == [(1, "喵"), (2, "汪")]


async def test_releasing_freezes_the_drafts_skill_references(agents: AgentRepository, owner: User) -> None:
    first = SkillReference(skill_id=uuid4().hex, version=1, name="annualized-252")
    second = SkillReference(skill_id=uuid4().hex, version=2, name="event-window")
    created = await agents.create(
        owner_id=owner.id,
        name=f"能力智能体-{uuid4().hex[:8]}",
        description="",
        subject="金融学",
        system_prompt="按能力说明工作",
        skill_refs=[first],
    )
    assert created is not None

    released = await agents.release(created.id, owner_id=owner.id)
    appended = await agents.write_draft(
        created.id,
        owner_id=owner.id,
        system_prompt="换一套能力",
        skill_refs=[second],
    )

    assert released is not None
    assert released.skill_refs == [first]
    assert appended is not None
    assert appended.skill_refs == [second]
    detail = await agents.detail(created.id, owner_id=owner.id)
    assert detail is not None
    assert [one.skill_refs for one in detail.versions] == [[first], [second]]


async def test_releasing_freezes_the_drafts_subagent_references(agents: AgentRepository, owner: User) -> None:
    first = SubagentReference(agent_id=uuid4().hex, version=1, name="volatility-expert")
    second = SubagentReference(agent_id=uuid4().hex, version=2, name="event-study-expert")
    created = await agents.create(
        owner_id=owner.id,
        name=f"场景智能体-{uuid4().hex[:8]}",
        description="",
        subject="金融学",
        system_prompt="按场景调度",
        subagent_refs=[first],
    )
    assert created is not None

    released = await agents.release(created.id, owner_id=owner.id)
    appended = await agents.write_draft(
        created.id,
        owner_id=owner.id,
        system_prompt="换一套场景",
        subagent_refs=[second],
    )

    assert released is not None
    assert released.subagent_refs == [first]
    assert appended is not None
    assert appended.subagent_refs == [second]
    detail = await agents.detail(created.id, owner_id=owner.id)
    assert detail is not None
    assert [one.subagent_refs for one in detail.versions] == [[first], [second]]


async def test_a_second_release_without_a_draft_changes_nothing(agents: AgentRepository, owner: User) -> None:
    agent_id = await _agent_of(agents, owner)
    assert await agents.release(agent_id, owner_id=owner.id) is not None

    assert await agents.release(agent_id, owner_id=owner.id) is None


async def test_editing_a_draft_twice_does_not_create_two_drafts(agents: AgentRepository, owner: User) -> None:
    """两个草稿意味着「我在改的是哪一份」没有答案。"""
    agent_id = await _agent_of(agents, owner)

    await agents.write_draft(agent_id, owner_id=owner.id, system_prompt="一改")
    await agents.write_draft(agent_id, owner_id=owner.id, system_prompt="二改")

    detail = await agents.detail(agent_id, owner_id=owner.id)
    assert detail is not None
    assert [(one.version, one.system_prompt) for one in detail.versions] == [(1, "二改")]


async def test_another_user_cannot_read_write_or_delete_my_agent(
    agents: AgentRepository, users: UserRepository, owner: User
) -> None:
    """越权的四条路径一次断完。任何一条漏了，别人拿到 id 就能改我的提示词。"""
    stranger = await _teacher(users)
    agent_id = await _agent_of(agents, owner)

    assert await agents.get(agent_id, owner_id=stranger.id) is None
    assert await agents.detail(agent_id, owner_id=stranger.id) is None
    assert await agents.write_draft(agent_id, owner_id=stranger.id, system_prompt="偷改") is None
    assert await agents.release(agent_id, owner_id=stranger.id) is None
    assert await agents.set_sharing(agent_id, owner_id=stranger.id, visibility=Visibility.GROUP, group_ids=[]) is None
    assert await agents.soft_delete(agent_id, owner_id=stranger.id) is False


async def test_a_deleted_agent_stays_in_mine_and_vanishes_everywhere_else(
    agents: AgentRepository, groups: GroupRepository, users: UserRepository, owner: User
) -> None:
    member = await _teacher(users)
    group = await _shared_group(groups, owner, member)
    agent_id = await _released(agents, owner)
    await agents.set_sharing(agent_id, owner_id=owner.id, visibility=Visibility.GROUP, group_ids=[group.id])
    assert agent_id in {one.id for one in await agents.list_available(member.id)}

    assert await agents.soft_delete(agent_id, owner_id=owner.id) is True

    assert agent_id in {one.agent.id for one in await agents.list_owned(owner.id)}
    assert agent_id not in {one.id for one in await agents.list_available(member.id)}
    assert agent_id not in {one.id for one in await agents.list_available(owner.id)}
    assert await agents.resolve(agent_id, user_id=owner.id) is None


async def test_a_private_agent_is_invisible_to_everyone_but_its_author(
    agents: AgentRepository, groups: GroupRepository, users: UserRepository, owner: User
) -> None:
    member = await _teacher(users)
    await _shared_group(groups, owner, member)
    agent_id = await _released(agents, owner)

    assert agent_id in {one.id for one in await agents.list_available(owner.id)}
    assert agent_id not in {one.id for one in await agents.list_available(member.id)}


async def test_group_sharing_is_seen_by_the_group_and_not_by_outsiders(
    agents: AgentRepository, groups: GroupRepository, users: UserRepository, owner: User
) -> None:
    """本期第一条主判据的仓储层对照。**双向**：只断言同组看得见是不够的。"""
    teammate = await _teacher(users)
    outsider = await _teacher(users)
    group = await _shared_group(groups, owner, teammate)
    # 别组的人真的在别的组里 —— 都在同一个组的话，「别组看不见」根本没被触发过
    outside = await groups.create(name=f"别组-{uuid4().hex[:8]}", owner_id=outsider.id)
    assert await groups.is_member(group_id=outside.id, user_id=teammate.id) is False
    agent_id = await _released(agents, owner)

    await agents.set_sharing(agent_id, owner_id=owner.id, visibility=Visibility.GROUP, group_ids=[group.id])

    assert agent_id in {one.id for one in await agents.list_available(teammate.id)}
    assert agent_id not in {one.id for one in await agents.list_available(outsider.id)}
    assert await agents.resolve(agent_id, user_id=teammate.id) is not None
    # 列表过滤对了而提交侧忘了查，是最典型的漏洞形状：别组从别处拿到 id 就能引用
    assert await agents.resolve(agent_id, user_id=outsider.id) is None


async def test_turning_sharing_back_to_private_takes_it_away_at_once(
    agents: AgentRepository, groups: GroupRepository, users: UserRepository, owner: User
) -> None:
    teammate = await _teacher(users)
    group = await _shared_group(groups, owner, teammate)
    agent_id = await _released(agents, owner)
    await agents.set_sharing(agent_id, owner_id=owner.id, visibility=Visibility.GROUP, group_ids=[group.id])

    await agents.set_sharing(agent_id, owner_id=owner.id, visibility=Visibility.PRIVATE, group_ids=[group.id])

    assert agent_id not in {one.id for one in await agents.list_available(teammate.id)}
    assert await agents.resolve(agent_id, user_id=teammate.id) is None


async def test_dropping_a_group_from_the_share_list_takes_it_away(
    agents: AgentRepository, groups: GroupRepository, users: UserRepository, owner: User
) -> None:
    teammate = await _teacher(users)
    group = await _shared_group(groups, owner, teammate)
    agent_id = await _released(agents, owner)
    await agents.set_sharing(agent_id, owner_id=owner.id, visibility=Visibility.GROUP, group_ids=[group.id])

    await agents.set_sharing(agent_id, owner_id=owner.id, visibility=Visibility.GROUP, group_ids=[])

    assert agent_id not in {one.id for one in await agents.list_available(teammate.id)}


async def test_sharing_with_two_groups_lists_the_agent_once(
    agents: AgentRepository, groups: GroupRepository, users: UserRepository, owner: User
) -> None:
    """多组共享走并集。JOIN 写法会让它在列表里出现两次，而那不报错。"""
    teammate = await _teacher(users)
    first = await _shared_group(groups, owner, teammate)
    second = await _shared_group(groups, owner, teammate)
    agent_id = await _released(agents, owner)

    await agents.set_sharing(agent_id, owner_id=owner.id, visibility=Visibility.GROUP, group_ids=[first.id, second.id])

    listed = [one for one in await agents.list_available(teammate.id) if one.id == agent_id]
    assert len(listed) == 1
    assert listed[0].source is AgentSource.GROUP


async def test_an_unreleased_agent_cannot_be_referenced_even_by_its_author(
    agents: AgentRepository, owner: User
) -> None:
    """草稿是没定稿的东西，连作者自己也不该在会话里引用到它。"""
    agent_id = await _agent_of(agents, owner)

    assert agent_id not in {one.id for one in await agents.list_available(owner.id)}
    assert await agents.resolve(agent_id, user_id=owner.id) is None


async def test_resolving_gives_the_latest_released_version(agents: AgentRepository, owner: User) -> None:
    agent_id = await _released(agents, owner, prompt="喵")
    await agents.write_draft(agent_id, owner_id=owner.id, system_prompt="汪")
    await agents.release(agent_id, owner_id=owner.id)

    resolved = await agents.resolve(agent_id, user_id=owner.id)

    assert resolved is not None
    assert (resolved.version, resolved.system_prompt) == (2, "汪")


async def test_a_draft_never_leaks_into_what_the_group_can_reference(
    agents: AgentRepository, groups: GroupRepository, users: UserRepository, owner: User
) -> None:
    """作者改到一半的内容不该被组员引用到 —— 引用的必须是定过稿的那一版。"""
    teammate = await _teacher(users)
    group = await _shared_group(groups, owner, teammate)
    agent_id = await _released(agents, owner, prompt="喵")
    await agents.set_sharing(agent_id, owner_id=owner.id, visibility=Visibility.GROUP, group_ids=[group.id])

    await agents.write_draft(agent_id, owner_id=owner.id, system_prompt="改到一半")

    resolved = await agents.resolve(agent_id, user_id=teammate.id)
    assert resolved is not None
    assert (resolved.version, resolved.system_prompt) == (1, "喵")


async def test_the_catalog_only_holds_approved_versions(
    agents: AgentRepository, reviews: ReviewRepository, users: UserRepository, owner: User
) -> None:
    reviewer = await _teacher(users)
    outsider = await _teacher(users)
    approved_agent = await _released(agents, owner)
    pending_agent = await _released(agents, owner)
    detail = await agents.detail(approved_agent, owner_id=owner.id)
    assert detail is not None
    await _approve(reviews, detail.versions[0].id, owner, reviewer)

    catalog = {one.id for one in await agents.list_catalog()}

    assert approved_agent in catalog
    assert pending_agent not in catalog
    # 广场上的东西谁都引用得到，哪怕作者从没共享给他所在的组
    assert approved_agent in {one.id for one in await agents.list_available(outsider.id)}
    assert pending_agent not in {one.id for one in await agents.list_available(outsider.id)}


async def test_the_catalog_version_takes_priority_for_every_viewer(
    agents: AgentRepository, reviews: ReviewRepository, users: UserRepository, owner: User
) -> None:
    """审核真的拦住每一次变更：作者发了 v2 而只审过 v1，广场上仍是 v1。"""
    reviewer = await _teacher(users)
    agent_id = await _released(agents, owner, prompt="第一版")
    detail = await agents.detail(agent_id, owner_id=owner.id)
    assert detail is not None
    await _approve(reviews, detail.versions[0].id, owner, reviewer)

    await agents.write_draft(agent_id, owner_id=owner.id, system_prompt="第二版")
    await agents.release(agent_id, owner_id=owner.id)

    listed = next(one for one in await agents.list_catalog() if one.id == agent_id)
    assert (listed.version, listed.system_prompt) == (1, "第一版")
    # 同时满足“自己的”和“广场的”时，广场优先，避免卡片与实际引用版本不一致
    resolved = await agents.resolve(agent_id, user_id=owner.id)
    assert resolved is not None
    assert (resolved.version, resolved.system_prompt) == (1, "第一版")


async def test_a_deleted_agent_leaves_the_catalog(
    agents: AgentRepository, reviews: ReviewRepository, users: UserRepository, owner: User
) -> None:
    reviewer = await _teacher(users)
    agent_id = await _released(agents, owner)
    detail = await agents.detail(agent_id, owner_id=owner.id)
    assert detail is not None
    await _approve(reviews, detail.versions[0].id, owner, reviewer)

    await agents.soft_delete(agent_id, owner_id=owner.id)

    assert agent_id not in {one.id for one in await agents.list_catalog()}


async def test_catalog_source_takes_priority_even_for_the_owner(
    agents: AgentRepository, reviews: ReviewRepository, users: UserRepository, owner: User
) -> None:
    """同一资源命中多个来源时，卡片标记采用优先级最高的广场。"""
    reviewer = await _teacher(users)
    agent_id = await _released(agents, owner)
    detail = await agents.detail(agent_id, owner_id=owner.id)
    assert detail is not None
    await _approve(reviews, detail.versions[0].id, owner, reviewer)

    mine = next(one for one in await agents.list_available(owner.id) if one.id == agent_id)
    theirs = next(one for one in await agents.list_available(reviewer.id) if one.id == agent_id)

    assert mine.source is AgentSource.CATALOG
    assert theirs.source is AgentSource.CATALOG


async def test_the_call_count_goes_up_by_one(agents: AgentRepository, owner: User) -> None:
    agent_id = await _released(agents, owner)

    await agents.count_call(agent_id)
    await agents.count_call(agent_id)

    listed = next(one for one in await agents.list_available(owner.id) if one.id == agent_id)
    assert listed.call_count == 2


async def test_a_malformed_identifier_is_a_miss_not_a_crash(agents: AgentRepository, owner: User) -> None:
    """标识来自 URL，解析不了就是「查不到」，不是 500。"""
    assert await agents.get("不是-uuid", owner_id=owner.id) is None
    assert await agents.detail("不是-uuid", owner_id=owner.id) is None
    assert await agents.resolve("不是-uuid", user_id=owner.id) is None
    assert await agents.soft_delete("不是-uuid", owner_id=owner.id) is False
    assert await agents.list_available("不是-uuid") == []
    assert await agents.list_owned("不是-uuid") == []


async def test_worker_loads_the_exact_frozen_subagent_version_even_after_delete(
    agents: AgentRepository, owner: User
) -> None:
    created = await agents.create(
        owner_id=owner.id,
        name=f"冻结版本-{uuid4().hex[:8]}",
        description="用于子图调度",
        subject="金融学",
        system_prompt="第一版",
    )
    assert created is not None
    assert await agents.release(created.id, owner_id=owner.id) is not None
    assert await agents.write_draft(created.id, owner_id=owner.id, system_prompt="第二版") is not None
    assert await agents.release(created.id, owner_id=owner.id) is not None
    assert await agents.soft_delete(created.id, owner_id=owner.id) is True

    frozen = await agents.load_subagent(created.id, 1)

    assert frozen is not None
    assert frozen.description == "用于子图调度"
    assert frozen.system_prompt == "第一版"
    assert await agents.load_subagent(created.id, 99) is None
