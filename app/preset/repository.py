"""智能体目录的读写：身份、版本序列、共享的组，以及三条可见性查询。

**越权过滤只写在这一层，端点一个 `where` 都不拼。** 本期最大的风险是「多看见了一条」
而不是「少看见一条」—— 少看见会有人来报（「我明明共享给他了他怎么看不到」），
多看见没有任何人会来报：别组的老师在广场里刷到一个不该看到的提示词，既不报错也不会
告诉你。把条件散在端点上，漏一处就是一个安静的泄露。

**三档可见性因此固定成三个名字说得清的方法**：

- `list_catalog`：平台目录（广场）。只有「有一个版本审核通过」的才在里面。
- `list_available`：我能引用的。我自己的 ∪ 共享给我所在组的 ∪ 平台目录。
- `list_owned`：我的全部，含各种状态与软删掉的那些。

**共享用相关子查询而不是 JOIN。** JOIN 到 `resource_groups` 上，一个共享给三个组的
agent 会在列表里出现三次；去重要么靠 `distinct` 要么靠人记得加 —— 而忘了加的症状
是列表里有重复项，不是报错。`EXISTS` 从形状上就不会多出行来。

**引用解析走的是 `list_available` 同一条语句**（`resolve`），不是另写一份。两份查询
迟早分叉，而分叉的方向一定是提交侧比列表侧宽 —— 那正好是「列表过滤对了、提交侧忘了
查」这个最典型的漏洞。
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import Select, Subquery, case, delete, exists, func, insert, literal, update
from sqlalchemy import select as sa_select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from agent.config import SkillReference, SubagentReference
from agent.subagent import SubagentDefinition
from group.model import GroupMemberRecord
from preset.model import (
    FIRST_VERSION,
    AgentRecord,
    AgentVersionRecord,
    ResourceGroupRecord,
    ResourceKind,
    ReviewRecord,
    ReviewStatus,
    VersionStatus,
    Visibility,
)
from user.model import UserRecord

logger = logging.getLogger(__name__)

# 「每个 agent 最新的那一版」那两条子查询取回来的七列。写全类型是为了在插列时
# 当场查得出错 —— 位置一旦错开，症状是提示词栏里显示的是版本号
VersionRow = tuple[
    UUID,
    UUID,
    int,
    str,
    list[dict[str, object]] | None,
    list[dict[str, object]] | None,
    datetime | None,
]


class AgentSource(StrEnum):
    """一个 agent 出现在「我能引用的」列表里，是凭哪一条。

    展示这一项是为了不让人误以为「组内的东西上了广场」。
    """

    OWNED = "owned"
    GROUP = "group"
    CATALOG = "catalog"


@dataclass(frozen=True)
class AgentVersion:
    """一个版本的内容。"""

    id: str
    version: int
    status: VersionStatus
    system_prompt: str
    skill_refs: list[SkillReference] | None
    subagent_refs: list[SubagentReference] | None
    created_at: datetime
    released_at: datetime | None


@dataclass(frozen=True)
class Agent:
    """一个智能体的身份行，不含内容。"""

    id: str
    owner_id: str
    name: str
    description: str
    subject: str
    visibility: Visibility
    call_count: int
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class AgentDetail:
    """作者视角的一个智能体：身份 + 全部版本 + 共享给了哪些组。

    **审核状态不在这里** —— 那是 `review.py` 的事，端点把两边拼起来。分开是因为
    审核记录按版本挂，而 skill / MCP 将来复用的是同一张表、不同的 `target_kind`。
    """

    agent: Agent
    owner_name: str
    versions: list[AgentVersion]
    group_ids: list[str]


@dataclass(frozen=True)
class AgentListing:
    """列表里的一个智能体，连同**这一档下该展示的那一版**。

    广场展示最新一个审核通过的版本，我的与组内展示最新一个已发布的版本 ——
    这两者可以不是同一版（作者发了 v3 但只有 v2 过审），而那正是审核的意义。

    **提示词全文就在这里。** 内容全部可见是定案（B4）：看不到提示词就判断不了
    一个 agent 值不值得用，而「共享出去的东西别人看得见内容」本来就是共享的含义。
    """

    id: str
    owner_id: str
    owner_name: str
    name: str
    description: str
    subject: str
    visibility: Visibility
    call_count: int
    version: int
    system_prompt: str
    skill_refs: list[SkillReference] | None
    subagent_refs: list[SubagentReference] | None
    source: AgentSource
    updated_at: datetime


@dataclass(frozen=True)
class ResolvedAgent:
    """一次引用解析的结果：这个人此刻确实能用它，用的是哪一版。"""

    agent_id: str
    name: str
    version: int
    system_prompt: str
    skill_refs: list[SkillReference] | None
    subagent_refs: list[SubagentReference] | None


class AgentRepository:
    """`agents` / `agent_versions` / `resource_groups` 三张表的读写。

    Args:
        engine: 到 Postgres 的异步引擎。
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def create(
        self,
        *,
        owner_id: str,
        name: str,
        description: str,
        subject: str,
        system_prompt: str,
        skill_refs: list[SkillReference] | None = None,
        subagent_refs: list[SubagentReference] | None = None,
    ) -> Agent | None:
        """建一个智能体，**连带它的 v1 草稿**。

        没有「只有身份没有内容」的中间态：那样的行在每一个列表查询里都要额外挡一次。

        Args:
            owner_id: 作者。
            name: 名称，同一作者名下唯一。
            description: 一句话说明。
            subject: 学科。
            system_prompt: v1 草稿的提示词。
            skill_refs: v1 草稿自带的 Skill 版本引用。
            subagent_refs: v1 草稿自带的子智能体版本引用。

        Returns:
            建出来的身份行；**名称在这个作者名下已被占用时返回 None** ——
            那是部分唯一索引挡下的，不是失败。
        """
        now = datetime.now(UTC)
        record = AgentRecord(
            id=uuid4(),
            owner_id=UUID(owner_id),
            name=name,
            description=description,
            subject=subject,
            visibility=Visibility.PRIVATE,
            created_at=now,
            updated_at=now,
        )
        version = AgentVersionRecord(
            id=uuid4(),
            agent_id=record.id,
            version=FIRST_VERSION,
            status=VersionStatus.DRAFT,
            system_prompt=system_prompt,
            skill_refs=_dump_refs(skill_refs),
            subagent_refs=_dump_refs(subagent_refs),
            created_at=now,
        )
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            session.add(record)
            try:
                # 身份行要先落库再加版本行：两张表之间只有外键、没有 relationship，
                # 而插入顺序只按 relationship 排 —— 一起 add 的话版本行可能排在前面，
                # 当场撞在外键上。两句仍在同一个事务里
                await session.flush()
                session.add(version)
                await session.commit()
            except IntegrityError:
                await session.rollback()
                return None
        logger.info("建智能体：agent_id=%s owner_id=%s", record.id.hex, owner_id)
        return _to_agent(record)

    async def get(self, agent_id: str, *, owner_id: str) -> Agent | None:
        """按 id 查一个**属于我的**智能体，别人的与不存在的是同一个答案。

        Args:
            agent_id: 智能体标识。
            owner_id: 当前用户。

        Returns:
            找到的身份行，否则 None。
        """
        identifier, owner = _parse(agent_id), _parse(owner_id)
        if identifier is None or owner is None:
            return None
        async with AsyncSession(self._engine) as session:
            record = await session.get(AgentRecord, identifier)
        if record is None or record.owner_id != owner:
            return None
        return _to_agent(record)

    async def detail(self, agent_id: str, *, owner_id: str) -> AgentDetail | None:
        """一个**属于我的**智能体的全貌：身份、全部版本、共享给了哪些组。

        Args:
            agent_id: 智能体标识。
            owner_id: 当前用户。

        Returns:
            全貌，否则 None。
        """
        identifier, owner = _parse(agent_id), _parse(owner_id)
        if identifier is None or owner is None:
            return None
        async with AsyncSession(self._engine) as session:
            record = await session.get(AgentRecord, identifier)
            if record is None or record.owner_id != owner:
                return None
            assembled = await self._assemble(session, [record])
        return assembled[0]

    async def update_meta(
        self,
        agent_id: str,
        *,
        owner_id: str,
        name: str,
        description: str,
        subject: str,
    ) -> Agent | None:
        """改元信息。**不产生新版本** —— 改名与改提示词是两件事。

        Args:
            agent_id: 智能体标识。
            owner_id: 当前用户。
            name: 新名称。
            description: 新说明。
            subject: 新学科。

        Returns:
            改完的身份行；不是我的、不存在，或新名称已被自己占用时返回 None。
        """
        identifier, owner = _parse(agent_id), _parse(owner_id)
        if identifier is None or owner is None:
            return None
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            record = await session.get(AgentRecord, identifier)
            if record is None or record.owner_id != owner or record.is_deleted:
                return None
            record.name = name
            record.description = description
            record.subject = subject
            record.updated_at = datetime.now(UTC)
            session.add(record)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                return None
        return _to_agent(record)

    async def write_draft(
        self,
        agent_id: str,
        *,
        owner_id: str,
        system_prompt: str,
        skill_refs: list[SkillReference] | None = None,
        subagent_refs: list[SubagentReference] | None = None,
    ) -> AgentVersion | None:
        """改草稿的内容；**没有草稿时追加下一个版本号的新草稿**。

        这就是「再改 = 追加一个新版本」那条状态转移。已发布的版本一个字都改不动 ——
        落进 run 快照的引用要照常读得回来。

        Args:
            agent_id: 智能体标识。
            owner_id: 当前用户。
            system_prompt: 新的提示词。
            skill_refs: 新草稿自带的 Skill 版本引用，整块替换。
            subagent_refs: 新草稿自带的子智能体版本引用，整块替换。

        Returns:
            改完（或新建）的那个草稿；不是我的、不存在或已删则 None。
        """
        identifier, owner = _parse(agent_id), _parse(owner_id)
        if identifier is None or owner is None:
            return None
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            agent = await session.get(AgentRecord, identifier)
            if agent is None or agent.owner_id != owner or agent.is_deleted:
                return None

            found = await session.exec(
                select(AgentVersionRecord).where(
                    col(AgentVersionRecord.agent_id) == identifier,
                    col(AgentVersionRecord.status) == VersionStatus.DRAFT,
                )
            )
            draft = found.first()
            if draft is None:
                highest = await session.exec(
                    select(func.max(col(AgentVersionRecord.version))).where(
                        col(AgentVersionRecord.agent_id) == identifier
                    )
                )
                draft = AgentVersionRecord(
                    id=uuid4(),
                    agent_id=identifier,
                    version=(highest.one() or 0) + 1,
                    status=VersionStatus.DRAFT,
                    system_prompt=system_prompt,
                    skill_refs=_dump_refs(skill_refs),
                    subagent_refs=_dump_refs(subagent_refs),
                    created_at=datetime.now(UTC),
                )
            else:
                draft.system_prompt = system_prompt
                draft.skill_refs = _dump_refs(skill_refs)
                draft.subagent_refs = _dump_refs(subagent_refs)
            agent.updated_at = datetime.now(UTC)
            session.add(draft)
            session.add(agent)
            await session.commit()
        return _to_version(draft)

    async def release(self, agent_id: str, *, owner_id: str) -> AgentVersion | None:
        """把草稿定稿。定稿之后内容冻结，组员从这一刻起看得见它。

        **状态是条件更新而不是「先读再写」**：两个标签页各点一次发布时，
        先读再写的那一份会把同一个草稿发布两遍。

        Args:
            agent_id: 智能体标识。
            owner_id: 当前用户。

        Returns:
            定稿的那个版本；没有草稿可发、不是我的或已删则 None。
        """
        identifier, owner = _parse(agent_id), _parse(owner_id)
        if identifier is None or owner is None:
            return None
        now = datetime.now(UTC)
        statement = (
            update(AgentVersionRecord)
            .where(
                col(AgentVersionRecord.agent_id) == identifier,
                col(AgentVersionRecord.status) == VersionStatus.DRAFT,
                exists(
                    sa_select(1)
                    .select_from(AgentRecord)
                    .where(
                        col(AgentRecord.id) == identifier,
                        col(AgentRecord.owner_id) == owner,
                        col(AgentRecord.is_deleted).is_(False),
                    )
                ),
            )
            .values(status=VersionStatus.RELEASED, released_at=now)
            .returning(
                col(AgentVersionRecord.id),
                col(AgentVersionRecord.version),
                col(AgentVersionRecord.system_prompt),
                col(AgentVersionRecord.skill_refs),
                col(AgentVersionRecord.subagent_refs),
                col(AgentVersionRecord.created_at),
            )
        )
        async with self._engine.begin() as connection:
            released = (await connection.execute(statement)).first()
            if released is None:
                return None
            await connection.execute(
                update(AgentRecord).where(col(AgentRecord.id) == identifier).values(updated_at=now)
            )
        logger.info("发布版本：agent_id=%s version=%s", agent_id, released[1])
        return AgentVersion(
            id=released[0].hex,
            version=released[1],
            status=VersionStatus.RELEASED,
            system_prompt=released[2],
            skill_refs=_load_skill_refs(released[3]),
            subagent_refs=_load_subagent_refs(released[4]),
            created_at=released[5],
            released_at=now,
        )

    async def set_sharing(
        self,
        agent_id: str,
        *,
        owner_id: str,
        visibility: Visibility,
        group_ids: Sequence[str],
    ) -> Agent | None:
        """设可见性与共享给哪些组，**整块替换**而不是增量。

        共享的组行在切回 `private` 时**留着**：可见性那一档才是闸门，两处都判的话
        「撤回再打开」会把老师之前选的组丢掉。列表查询同时要求 `visibility = group`
        与这里有行，缺一不可。

        Args:
            agent_id: 智能体标识。
            owner_id: 当前用户。
            visibility: 私有还是组内。
            group_ids: 共享给哪些组；调用方负责确认这些组当前用户都在里面。

        Returns:
            改完的身份行；不是我的、不存在或已删则 None。
        """
        identifier, owner = _parse(agent_id), _parse(owner_id)
        if identifier is None or owner is None:
            return None
        wanted = {parsed for parsed in (_parse(one) for one in group_ids) if parsed is not None}
        changing = (
            update(AgentRecord)
            .where(
                col(AgentRecord.id) == identifier,
                col(AgentRecord.owner_id) == owner,
                col(AgentRecord.is_deleted).is_(False),
            )
            .values(visibility=visibility, updated_at=datetime.now(UTC))
            .returning(col(AgentRecord.id))
        )
        # 三句在同一个事务里：分开的话，中间失败会留下「可见性已改、共享的组还是旧的」
        async with self._engine.begin() as connection:
            if (await connection.execute(changing)).first() is None:
                return None
            await connection.execute(
                delete(ResourceGroupRecord).where(
                    col(ResourceGroupRecord.resource_kind) == ResourceKind.AGENT,
                    col(ResourceGroupRecord.resource_id) == identifier,
                )
            )
            if wanted:
                await connection.execute(
                    insert(ResourceGroupRecord),
                    [
                        {"resource_kind": ResourceKind.AGENT, "resource_id": identifier, "group_id": one}
                        for one in sorted(wanted)
                    ],
                )
        logger.info("设共享：agent_id=%s visibility=%s groups=%d", agent_id, visibility.value, len(wanted))
        return await self.get(agent_id, owner_id=owner_id)

    async def soft_delete(self, agent_id: str, *, owner_id: str) -> bool:
        """软删一个智能体：作者的「我的」里还看得到，别处一律当它不存在。

        **不硬删**：run 快照里躺着这个 `agent_id`，那是历史。

        Args:
            agent_id: 智能体标识。
            owner_id: 当前用户。

        Returns:
            这一次是否真的删了。不是我的、不存在或已经删过则 False。
        """
        identifier, owner = _parse(agent_id), _parse(owner_id)
        if identifier is None or owner is None:
            return False
        statement = (
            update(AgentRecord)
            .where(
                col(AgentRecord.id) == identifier,
                col(AgentRecord.owner_id) == owner,
                col(AgentRecord.is_deleted).is_(False),
            )
            .values(is_deleted=True, updated_at=datetime.now(UTC))
            .returning(col(AgentRecord.id))
        )
        async with self._engine.begin() as connection:
            deleted = (await connection.execute(statement)).first()
        if deleted is None:
            return False
        logger.info("软删智能体：agent_id=%s by=%s", agent_id, owner_id)
        return True

    async def list_catalog(self) -> list[AgentListing]:
        """平台目录（广场）：**有一个版本审核通过**的那些，展示最新过审的那一版。

        排序是「调用数、发布时间」两项，没有算法 —— 学院内部平台上 agent 是几十个
        量级，推荐系统在这个规模上解决不了任何问题。

        Returns:
            广场上的每个 agent 一行。
        """
        approved = _latest_approved()
        statement = (
            _listing_select(
                version=approved.c.version,
                system_prompt=approved.c.system_prompt,
                skill_refs=approved.c.skill_refs,
                subagent_refs=approved.c.subagent_refs,
                source=literal(AgentSource.CATALOG.value),
            )
            .join(UserRecord, onclause=col(UserRecord.id) == col(AgentRecord.owner_id))
            .join(approved, onclause=approved.c.agent_id == col(AgentRecord.id))
            .where(col(AgentRecord.is_deleted).is_(False))
            .order_by(col(AgentRecord.call_count).desc(), approved.c.released_at.desc())
        )
        return await self._listing(statement)

    async def list_available(self, user_id: str) -> list[AgentListing]:
        """我此刻能引用的全部：我自己的 ∪ 共享给我所在组的 ∪ 平台目录。

        Args:
            user_id: 当前用户。

        Returns:
            每个 agent 一行，带着它是凭哪一条进来的（`source`）。
        """
        owner = _parse(user_id)
        if owner is None:
            return []
        statement = self._available_statement(owner).order_by(col(AgentRecord.name))
        return await self._listing(statement)

    async def list_owned(self, user_id: str) -> list[AgentDetail]:
        """我的全部智能体，**含软删掉的那些**，最近改动的排前面。

        软删的行留在这里是为了让「删掉之后别处都没了」有一个可核对的对照面 ——
        行还在，只是任何别人的查询都够不着它。调用方按 `is_deleted` 决定显不显示。

        **版本与共享的组一次批量取回**，不是每个 agent 各查一遍：作者手上几十个 agent
        就是几十次往返，而那种慢法在开发机上量不出来。

        Args:
            user_id: 当前用户。

        Returns:
            每个 agent 一行，带全部版本与共享的组。
        """
        owner = _parse(user_id)
        if owner is None:
            return []
        async with AsyncSession(self._engine) as session:
            found = await session.exec(
                select(AgentRecord)
                .where(col(AgentRecord.owner_id) == owner)
                .order_by(col(AgentRecord.updated_at).desc())
            )
            return await self._assemble(session, list(found.all()))

    async def _assemble(self, session: AsyncSession, records: list[AgentRecord]) -> list[AgentDetail]:
        """给一批身份行配上它们的版本与共享的组。"""
        if not records:
            return []
        identifiers = [one.id for one in records]
        versions = await session.exec(
            select(AgentVersionRecord)
            .where(col(AgentVersionRecord.agent_id).in_(identifiers))
            .order_by(col(AgentVersionRecord.version))
        )
        groups = await session.exec(
            select(ResourceGroupRecord).where(
                col(ResourceGroupRecord.resource_kind) == ResourceKind.AGENT,
                col(ResourceGroupRecord.resource_id).in_(identifiers),
            )
        )
        names = await session.exec(
            select(col(UserRecord.id), col(UserRecord.name)).where(
                col(UserRecord.id).in_([one.owner_id for one in records])
            )
        )
        by_agent: dict[UUID, list[AgentVersion]] = {one: [] for one in identifiers}
        for version in versions.all():
            by_agent[version.agent_id].append(_to_version(version))
        shared: dict[UUID, list[str]] = {one: [] for one in identifiers}
        for row in groups.all():
            shared[row.resource_id].append(row.group_id.hex)
        owner_name = dict(names.all())
        return [
            AgentDetail(
                agent=_to_agent(one),
                owner_name=owner_name.get(one.owner_id, ""),
                versions=by_agent[one.id],
                group_ids=sorted(shared[one.id]),
            )
            for one in records
        ]

    async def resolve(self, agent_id: str, *, user_id: str) -> ResolvedAgent | None:
        """解析一次引用：这个人此刻能不能用它、用的是哪一版。

        **走的是 `list_available` 同一条语句**，因此列表看得见什么就引用得到什么，
        一行都不多。解析不出来的一律由调用方翻成 422，不静默回退默认提示词 ——
        静默回退跑得完、不报错，唯一的症状是回答变了味。

        Args:
            agent_id: 被引用的智能体。
            user_id: 提交的人。

        Returns:
            解析结果；不存在、已删、没发布过、或这个人够不着它时返回 None。
        """
        identifier, owner = _parse(agent_id), _parse(user_id)
        if identifier is None or owner is None:
            return None
        statement = self._available_statement(owner).where(col(AgentRecord.id) == identifier)
        async with self._engine.connect() as connection:
            found = (await connection.execute(statement)).mappings().first()
        if found is None:
            return None
        return ResolvedAgent(
            agent_id=found["id"].hex,
            name=found["name"],
            version=found["version"],
            system_prompt=found["system_prompt"],
            skill_refs=_load_skill_refs(found["skill_refs"]),
            subagent_refs=_load_subagent_refs(found["subagent_refs"]),
        )

    async def load_subagent(self, agent_id: str, version: int) -> SubagentDefinition | None:
        """按快照中的稳定标识与版本读取子智能体内容。

        这里刻意不判断当前可见性与软删除状态：提交侧已经完成授权并冻结版本，worker
        晚几分钟执行时不能因为作者刚好撤回共享而改变同一次提交的结果。
        """
        identifier = _parse(agent_id)
        if identifier is None:
            return None
        statement = cast(
            Select[tuple[object, ...]],
            sa_select(
                col(AgentRecord.description).label("description"),
                col(AgentVersionRecord.system_prompt).label("system_prompt"),
            )
            .join(AgentVersionRecord, onclause=col(AgentVersionRecord.agent_id) == col(AgentRecord.id))
            .where(col(AgentRecord.id) == identifier, col(AgentVersionRecord.version) == version),
        )
        async with self._engine.connect() as connection:
            found = (await connection.execute(statement)).mappings().first()
        if found is None:
            return None
        return SubagentDefinition(
            description=found["description"],
            system_prompt=found["system_prompt"],
        )

    async def count_call(self, agent_id: str) -> None:
        """给调用计数 +1。

        **原子自增而不是「先读再写」**：两次提交撞在一起时，先读再写会丢掉一次。
        不去重、不实时是定案 —— 它的用途是判断哪些资源值得平台收编，不是排行榜。

        Args:
            agent_id: 被引用的智能体。
        """
        identifier = _parse(agent_id)
        if identifier is None:
            return
        async with self._engine.begin() as connection:
            await connection.execute(
                update(AgentRecord)
                .where(col(AgentRecord.id) == identifier)
                .values(call_count=col(AgentRecord.call_count) + 1)
            )

    def _available_statement(self, user_id: UUID) -> Select[tuple[object, ...]]:
        """「我能引用的」那一条语句，`list_available` 与 `resolve` 共用。

        三条来路各带各的版本：我自己的与组内共享的看最新**已发布**版，
        平台目录看最新**过审**版 —— 作者发了 v3 而只有 v2 过审时，这两者不是同一版，
        而那正是审核的意义。
        """
        released = _latest_released()
        approved = _latest_approved()
        mine = col(AgentRecord.owner_id) == user_id
        group_shared = (col(AgentRecord.visibility) == Visibility.GROUP) & _shared_with(user_id)
        # 组内与自己的都要求「有一个已发布的版本」：草稿是没定稿的东西，
        # 连作者自己也不该在会话里引用到它
        first_hand = (mine | group_shared) & released.c.version_id.is_not(None)
        in_catalog = approved.c.version_id.is_not(None)
        return (
            _listing_select(
                version=case((first_hand, released.c.version), else_=approved.c.version),
                system_prompt=case((first_hand, released.c.system_prompt), else_=approved.c.system_prompt),
                skill_refs=case((first_hand, released.c.skill_refs), else_=approved.c.skill_refs),
                subagent_refs=case((first_hand, released.c.subagent_refs), else_=approved.c.subagent_refs),
                source=case(
                    (mine, AgentSource.OWNED.value),
                    (group_shared, AgentSource.GROUP.value),
                    else_=AgentSource.CATALOG.value,
                ),
            )
            .join(UserRecord, onclause=col(UserRecord.id) == col(AgentRecord.owner_id))
            .outerjoin(released, onclause=released.c.agent_id == col(AgentRecord.id))
            .outerjoin(approved, onclause=approved.c.agent_id == col(AgentRecord.id))
            .where(col(AgentRecord.is_deleted).is_(False), first_hand | in_catalog)
        )

    async def _listing(self, statement: Select[tuple[object, ...]]) -> list[AgentListing]:
        async with self._engine.connect() as connection:
            found = (await connection.execute(statement)).mappings().all()
        return [
            AgentListing(
                id=row["id"].hex,
                owner_id=row["owner_id"].hex,
                owner_name=row["owner_name"],
                name=row["name"],
                description=row["description"],
                subject=row["subject"],
                visibility=row["visibility"],
                call_count=row["call_count"],
                version=row["version"],
                system_prompt=row["system_prompt"],
                skill_refs=_load_skill_refs(row["skill_refs"]),
                subagent_refs=_load_subagent_refs(row["subagent_refs"]),
                source=AgentSource(row["source"]),
                updated_at=row["updated_at"],
            )
            for row in found
        ]


def _listing_select(
    *,
    version: ColumnElement[int],
    system_prompt: ColumnElement[str],
    skill_refs: ColumnElement[list[dict[str, object]] | None],
    subagent_refs: ColumnElement[list[dict[str, object]] | None],
    source: ColumnElement[str],
) -> Select[tuple[object, ...]]:
    """列表行的那十四列。

    **按标签取值而不是按位置**：十四列的位置索引会在某次插列时整体错位一格，
    而错位的症状是「说明栏里显示的是学科」，没有任何一处报错。
    """
    return sa_select(
        col(AgentRecord.id).label("id"),
        col(AgentRecord.owner_id).label("owner_id"),
        col(UserRecord.name).label("owner_name"),
        col(AgentRecord.name).label("name"),
        col(AgentRecord.description).label("description"),
        col(AgentRecord.subject).label("subject"),
        col(AgentRecord.visibility).label("visibility"),
        col(AgentRecord.call_count).label("call_count"),
        version.label("version"),
        system_prompt.label("system_prompt"),
        skill_refs.label("skill_refs"),
        subagent_refs.label("subagent_refs"),
        source.label("source"),
        col(AgentRecord.updated_at).label("updated_at"),
    )


def _version_select() -> Select[VersionRow]:
    """版本行上被上面几条查询用到的那七列。"""
    return sa_select(
        col(AgentVersionRecord.agent_id).label("agent_id"),
        col(AgentVersionRecord.id).label("version_id"),
        col(AgentVersionRecord.version).label("version"),
        col(AgentVersionRecord.system_prompt).label("system_prompt"),
        col(AgentVersionRecord.skill_refs).label("skill_refs"),
        col(AgentVersionRecord.subagent_refs).label("subagent_refs"),
        col(AgentVersionRecord.released_at).label("released_at"),
    )


def _latest_released() -> Subquery:
    """每个 agent 最新的那个已发布版本。"""
    return _latest(_version_select().where(col(AgentVersionRecord.status) == VersionStatus.RELEASED))


def _latest_approved() -> Subquery:
    """每个 agent 最新的那个**审核通过**的版本。

    盯着版本审而不是盯着 agent 审：审过一次之后作者随便改的话，等于没有审核。
    """
    return _latest(
        _version_select()
        .join(ReviewRecord, onclause=col(ReviewRecord.target_id) == col(AgentVersionRecord.id))
        .where(
            col(ReviewRecord.target_kind) == ResourceKind.AGENT,
            col(ReviewRecord.status) == ReviewStatus.APPROVED,
        )
    )


def _latest(statement: Select[VersionRow]) -> Subquery:
    """把一条版本查询收成「每个 agent 只留版本号最大的那一行」。

    走 `DISTINCT ON` 而不是「按 agent 分组取 max 再回连」：后者要两次扫表，
    且回连条件写错时不报错，只是同一个 agent 冒出两行。
    """
    return (
        statement.distinct(col(AgentVersionRecord.agent_id))
        .order_by(col(AgentVersionRecord.agent_id), col(AgentVersionRecord.version).desc())
        .subquery()
    )


def _shared_with(user_id: UUID) -> ColumnElement[bool]:
    """这个 agent 有没有共享给「这个人所在的某个组」。

    **相关子查询而不是 JOIN**：共享给三个组的 agent 用 JOIN 会在列表里出现三次，
    而去重靠的是有人记得加 `distinct`。多组走并集就是这个 `EXISTS` 的天然语义。
    """
    return exists(
        sa_select(1)
        .select_from(ResourceGroupRecord)
        .join(GroupMemberRecord, onclause=col(GroupMemberRecord.group_id) == col(ResourceGroupRecord.group_id))
        .where(
            col(ResourceGroupRecord.resource_kind) == ResourceKind.AGENT,
            col(ResourceGroupRecord.resource_id) == col(AgentRecord.id),
            col(GroupMemberRecord.user_id) == user_id,
        )
    )


def _to_agent(record: AgentRecord) -> Agent:
    return Agent(
        id=record.id.hex,
        owner_id=record.owner_id.hex,
        name=record.name,
        description=record.description,
        subject=record.subject,
        visibility=record.visibility,
        call_count=record.call_count,
        is_deleted=record.is_deleted,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _to_version(record: AgentVersionRecord) -> AgentVersion:
    return AgentVersion(
        id=record.id.hex,
        version=record.version,
        status=record.status,
        system_prompt=record.system_prompt,
        skill_refs=_load_skill_refs(record.skill_refs),
        subagent_refs=_load_subagent_refs(record.subagent_refs),
        created_at=record.created_at,
        released_at=record.released_at,
    )


def _dump_refs(
    references: list[SkillReference] | list[SubagentReference] | None,
) -> list[dict[str, object]] | None:
    """把结构化引用写成 JSONB 能直接接收的值。"""
    if not references:
        return None
    return [one.model_dump() for one in references]


def _load_skill_refs(raw: list[dict[str, object]] | None) -> list[SkillReference] | None:
    """把 JSONB 与历史 NULL 还原成结构化引用。"""
    if not raw:
        return None
    return [SkillReference.model_validate(one) for one in raw]


def _load_subagent_refs(raw: list[dict[str, object]] | None) -> list[SubagentReference] | None:
    """把 JSONB 与历史 NULL 还原成结构化子智能体引用。"""
    if not raw:
        return None
    return [SubagentReference.model_validate(one) for one in raw]


def _parse(identifier: str) -> UUID | None:
    """标识来自 URL 与 session，解析不了就是「查不到」，不是 500。"""
    try:
        return UUID(identifier)
    except ValueError:
        return None
