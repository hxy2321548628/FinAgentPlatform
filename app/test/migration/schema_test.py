"""迁移本身的测试：升得上去、退得回来、不碰已有的行。

**up / down 全部跑在一个用完就删的空库上**，不在测试库上跑 —— `downgrade` 会把同一批
用例正在用的表整个删掉。这条隔离本身就是本次要验的东西之一。
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import uuid4

import psycopg
import pytest
from alembic import command

from store.postgres import DRIVER, NATIVE_DRIVER
from test.conftest import (
    PROBE_TIMEOUT_SECOND,
    SKIP_POSTGRES,
    alembic_config,
    drop_database,
    ensure_database,
    store_dsn,
)

# 至今建起来的全部业务表。downgrade 之后一张都不该剩
PLATFORM_TABLE = (
    "users",
    "threads",
    "runs",
    "run_events",
    "groups",
    "user_groups",
    "group_join_requests",
    "agents",
    "agent_versions",
    "reviews",
    "resource_groups",
    "skills",
    "skill_versions",
)

# 建用户模型之前的那一版。已有的 runs 行就是在这一版上写下的
BEFORE_USER_MODEL = "0002_run_events"

# 给 runs.thread_id 补外键之前的那一版
BEFORE_RUN_THREAD_FOREIGN_KEY = "0003_user_thread"

# 给 runs 补当次配置快照之前的那一版
BEFORE_RUN_AGENT_CONFIG = "0009_drop_artifacts"

# 建智能体目录四张表之前的那一版
BEFORE_AGENT_CATALOG = "0010_run_agent_config"

# 建 skill 目录两张表、给 agent 版本补 skill 引用之前的那一版
BEFORE_SKILL_CATALOG = "0011_agent_catalog"


@pytest.fixture
def scratch() -> Iterator[str]:
    """一个用完就删的空库，只给这个文件用。

    Yields:
        库名。
    """
    name = f"zuel_migration_{uuid4().hex[:8]}"
    try:
        ensure_database(name)
    except psycopg.Error:
        pytest.skip(SKIP_POSTGRES)
    try:
        yield name
    finally:
        drop_database(name)


def _connect(database: str) -> psycopg.Connection[tuple[object, ...]]:
    return psycopg.connect(
        store_dsn(NATIVE_DRIVER, database=database), connect_timeout=PROBE_TIMEOUT_SECOND, autocommit=True
    )


def _upgrade(database: str, revision: str) -> None:
    command.upgrade(alembic_config(store_dsn(DRIVER, database=database)), revision)


def _downgrade(database: str, revision: str) -> None:
    command.downgrade(alembic_config(store_dsn(DRIVER, database=database)), revision)


def _table(database: str) -> set[str]:
    with _connect(database) as connection:
        found = connection.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'").fetchall()
    return {str(one[0]) for one in found}


def _index(database: str, table: str) -> dict[str, str]:
    with _connect(database) as connection:
        found = connection.execute(
            "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'public' AND tablename = %s",
            (table,),
        ).fetchall()
    return {str(one[0]): str(one[1]) for one in found}


def _column(database: str, table: str) -> set[str]:
    with _connect(database) as connection:
        found = connection.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = %s",
            (table,),
        ).fetchall()
    return {str(one[0]) for one in found}


def _insert_user(connection: psycopg.Connection[tuple[object, ...]], user_id: str) -> None:
    connection.execute(
        "INSERT INTO users (id, name, password_hash, role, is_active, created_at)"
        " VALUES (%s, %s, 'x', 'teacher', true, %s)",
        (user_id, f"u-{user_id[:8]}", datetime.now(UTC)),
    )


def _insert_group(
    connection: psycopg.Connection[tuple[object, ...]], group_id: str, owner_id: str, *, code: str | None = None
) -> None:
    connection.execute(
        "INSERT INTO groups (id, name, owner_id, invite_code, created_at) VALUES (%s, %s, %s, %s, %s)",
        (group_id, f"g-{group_id[:8]}", owner_id, code or group_id[:8].upper(), datetime.now(UTC)),
    )


def _insert_request(
    connection: psycopg.Connection[tuple[object, ...]],
    group_id: str,
    user_id: str,
    *,
    status: str = "pending",
) -> None:
    connection.execute(
        "INSERT INTO group_join_requests (id, group_id, user_id, status, created_at) VALUES (%s, %s, %s, %s, %s)",
        (uuid4().hex, group_id, user_id, status, datetime.now(UTC)),
    )


def _insert_thread(connection: psycopg.Connection[tuple[object, ...]], thread_id: str, user_id: str) -> None:
    now = datetime.now(UTC)
    connection.execute(
        "INSERT INTO threads (id, user_id, title, agent_config, created_at, updated_at)"
        " VALUES (%s, %s, '', '{}', %s, %s)",
        (thread_id, user_id, now, now),
    )


def _insert_run(connection: psycopg.Connection[tuple[object, ...]], run_id: str, thread_id: str) -> None:
    connection.execute(
        "INSERT INTO runs (id, thread_id, status, tokens_cache_read, tokens_uncached, tokens_output, started_at)"
        " VALUES (%s, %s, 'succeeded', 0, 0, 0, %s)",
        (run_id, thread_id, datetime.now(UTC)),
    )


def test_upgrade_then_downgrade_leaves_no_platform_table(scratch: str) -> None:
    _upgrade(scratch, "head")
    assert set(PLATFORM_TABLE) <= _table(scratch)

    _downgrade(scratch, "base")
    assert not set(PLATFORM_TABLE) & _table(scratch)


def test_upgrade_creates_the_thread_index_of_the_architecture(scratch: str) -> None:
    """架构 §6.2 索引表里属于 threads 的那一条：`(user_id, updated_at DESC)`。"""
    _upgrade(scratch, "head")

    definition = _index(scratch, "threads")
    assert "ix_threads_user_updated" in definition
    assert "updated_at DESC" in definition["ix_threads_user_updated"]


def test_user_name_is_unique(scratch: str) -> None:
    _upgrade(scratch, "head")

    with _connect(scratch) as connection:
        connection.execute(
            "INSERT INTO users (id, name, password_hash, role, is_active, created_at)"
            " VALUES (%s, '重名', 'x', 'teacher', true, %s)",
            (uuid4().hex, datetime.now(UTC)),
        )
        with pytest.raises(psycopg.errors.UniqueViolation):
            connection.execute(
                "INSERT INTO users (id, name, password_hash, role, is_active, created_at)"
                " VALUES (%s, '重名', 'y', 'student', true, %s)",
                (uuid4().hex, datetime.now(UTC)),
            )


def test_existing_run_rows_survive_the_upgrade(scratch: str) -> None:
    """P2 留下的 run 行没有归属，迁移只建表不回填 —— 它们必须原样还在，`user_id` 仍为空。"""
    _upgrade(scratch, BEFORE_USER_MODEL)
    orphan = uuid4().hex
    with _connect(scratch) as connection:
        _insert_run(connection, orphan, uuid4().hex)

    _upgrade(scratch, "head")

    with _connect(scratch) as connection:
        found = connection.execute("SELECT user_id FROM runs WHERE id = %s", (orphan,)).fetchone()
    assert found is not None
    assert found[0] is None


def test_run_agent_config_migration_upgrades_and_downgrades_without_touching_old_rows(scratch: str) -> None:
    _upgrade(scratch, BEFORE_RUN_AGENT_CONFIG)
    user_id, thread_id, old_run = uuid4().hex, uuid4().hex, uuid4().hex
    with _connect(scratch) as connection:
        _insert_user(connection, user_id)
        _insert_thread(connection, thread_id, user_id)
        _insert_run(connection, old_run, thread_id)

    _upgrade(scratch, "head")

    assert "agent_config" in _column(scratch, "runs")
    with _connect(scratch) as connection:
        old_config = connection.execute("SELECT agent_config FROM runs WHERE id = %s", (old_run,)).fetchone()
        # 新版仍允许显式列名的旧 INSERT 不带 agent_config。
        another = uuid4().hex
        _insert_run(connection, another, thread_id)
        another_config = connection.execute("SELECT agent_config FROM runs WHERE id = %s", (another,)).fetchone()
    assert old_config == (None,)
    assert another_config == (None,)

    _downgrade(scratch, BEFORE_RUN_AGENT_CONFIG)

    assert "agent_config" not in _column(scratch, "runs")
    with _connect(scratch) as connection:
        assert connection.execute("SELECT 1 FROM runs WHERE id = %s", (old_run,)).fetchone() is not None


def test_a_new_run_must_point_at_an_existing_thread(scratch: str) -> None:
    """0004 之后 `runs.thread_id` 受外键约束：NOT VALID 只放过历史行。

    这条外键推迟到 0004 才加，是因为在 0003 那一刻它约束不住任何东西 ——
    `threads` 还是空的，而提交 run 的入口仍只建目录不落表。
    """
    _upgrade(scratch, "head")

    with _connect(scratch) as connection, pytest.raises(psycopg.errors.ForeignKeyViolation):
        _insert_run(connection, uuid4().hex, uuid4().hex)


def test_a_run_written_before_the_foreign_key_is_left_alone(scratch: str) -> None:
    """NOT VALID 的另一半：历史行不追究，`alembic upgrade head` 不会栽在它们身上。"""
    _upgrade(scratch, BEFORE_RUN_THREAD_FOREIGN_KEY)
    orphan = uuid4().hex
    with _connect(scratch) as connection:
        _insert_run(connection, orphan, uuid4().hex)

    _upgrade(scratch, "head")

    with _connect(scratch) as connection:
        assert connection.execute("SELECT 1 FROM runs WHERE id = %s", (orphan,)).fetchone() is not None


def test_a_thread_must_point_at_an_existing_user(scratch: str) -> None:
    _upgrade(scratch, "head")

    with _connect(scratch) as connection, pytest.raises(psycopg.errors.ForeignKeyViolation):
        _insert_thread(connection, uuid4().hex, uuid4().hex)


def test_a_group_must_point_at_an_existing_owner(scratch: str) -> None:
    """组主是外键。没有它的话，禁用一个教师账号之后它的组会变成谁也管不了的孤儿。"""
    _upgrade(scratch, "head")

    with _connect(scratch) as connection, pytest.raises(psycopg.errors.ForeignKeyViolation):
        _insert_group(connection, uuid4().hex, uuid4().hex)


def test_the_same_invite_code_cannot_be_taken_twice(scratch: str) -> None:
    """邀请码是注册时唯一的入组依据 —— 撞码等于把学生发进别人的组。"""
    _upgrade(scratch, "head")

    with _connect(scratch) as connection:
        owner = uuid4().hex
        _insert_user(connection, owner)
        _insert_group(connection, uuid4().hex, owner, code="SAME")
        with pytest.raises(psycopg.errors.UniqueViolation):
            _insert_group(connection, uuid4().hex, owner, code="SAME")


def test_a_user_cannot_join_the_same_group_twice(scratch: str) -> None:
    """成员关系是复合主键。重复的行会让名册出现两个同一个人。"""
    _upgrade(scratch, "head")

    with _connect(scratch) as connection:
        owner, group = uuid4().hex, uuid4().hex
        _insert_user(connection, owner)
        _insert_group(connection, group, owner)
        connection.execute("INSERT INTO user_groups (user_id, group_id) VALUES (%s, %s)", (owner, group))
        with pytest.raises(psycopg.errors.UniqueViolation):
            connection.execute("INSERT INTO user_groups (user_id, group_id) VALUES (%s, %s)", (owner, group))


def test_a_user_cannot_have_two_pending_requests_for_one_group(scratch: str) -> None:
    """连点两次申请只该留下一条待办，否则组主的审批列表里全是同一个人。"""
    _upgrade(scratch, "head")

    with _connect(scratch) as connection:
        owner, group = uuid4().hex, uuid4().hex
        _insert_user(connection, owner)
        _insert_group(connection, group, owner)
        _insert_request(connection, group, owner)
        with pytest.raises(psycopg.errors.UniqueViolation):
            _insert_request(connection, group, owner)


def test_a_rejected_applicant_can_apply_again(scratch: str) -> None:
    """唯一约束只盖 pending 那一段。被否决之后再也申请不了，那是把人永久挡在门外。"""
    _upgrade(scratch, "head")

    with _connect(scratch) as connection:
        owner, group = uuid4().hex, uuid4().hex
        _insert_user(connection, owner)
        _insert_group(connection, group, owner)
        _insert_request(connection, group, owner, status="rejected")

        _insert_request(connection, group, owner)

        found = connection.execute(
            "SELECT count(*) FROM group_join_requests WHERE group_id = %s AND user_id = %s", (group, owner)
        ).fetchone()
    assert found is not None
    assert found[0] == 2


def _insert_agent(
    connection: psycopg.Connection[tuple[object, ...]],
    agent_id: str,
    owner_id: str,
    *,
    name: str | None = None,
    is_deleted: bool = False,
) -> None:
    now = datetime.now(UTC)
    connection.execute(
        "INSERT INTO agents (id, owner_id, name, description, subject, visibility,"
        " call_count, is_deleted, created_at, updated_at)"
        " VALUES (%s, %s, %s, '', '', 'private', 0, %s, %s, %s)",
        (agent_id, owner_id, name or f"a-{agent_id[:8]}", is_deleted, now, now),
    )


def _insert_version(
    connection: psycopg.Connection[tuple[object, ...]],
    version_id: str,
    agent_id: str,
    *,
    version: int = 1,
    status: str = "draft",
) -> None:
    connection.execute(
        "INSERT INTO agent_versions (id, agent_id, version, status, system_prompt, created_at)"
        " VALUES (%s, %s, %s, %s, '', %s)",
        (version_id, agent_id, version, status, datetime.now(UTC)),
    )


def _insert_review(
    connection: psycopg.Connection[tuple[object, ...]],
    target_id: str,
    submitter: str,
    *,
    status: str = "pending",
) -> None:
    connection.execute(
        "INSERT INTO reviews (id, target_kind, target_id, status, responsibility_confirmed,"
        " submitted_by, created_at)"
        " VALUES (%s, 'agent', %s, %s, true, %s, %s)",
        (uuid4().hex, target_id, status, submitter, datetime.now(UTC)),
    )


def test_agent_catalog_tables_are_created_without_touching_existing_rows(scratch: str) -> None:
    """0011 只建表。这一版之前写下的 run 与会话必须原样还在。"""
    _upgrade(scratch, BEFORE_AGENT_CATALOG)
    user_id, thread_id, run_id = uuid4().hex, uuid4().hex, uuid4().hex
    with _connect(scratch) as connection:
        _insert_user(connection, user_id)
        _insert_thread(connection, thread_id, user_id)
        _insert_run(connection, run_id, thread_id)

    _upgrade(scratch, "head")

    with _connect(scratch) as connection:
        assert connection.execute("SELECT 1 FROM runs WHERE id = %s", (run_id,)).fetchone() is not None

    _downgrade(scratch, BEFORE_AGENT_CATALOG)

    assert not {"agents", "agent_versions", "reviews", "resource_groups"} & _table(scratch)
    with _connect(scratch) as connection:
        assert connection.execute("SELECT 1 FROM runs WHERE id = %s", (run_id,)).fetchone() is not None


def test_one_author_cannot_use_the_same_agent_name_twice(scratch: str) -> None:
    """同一作者名下唯一。广场卡片带着作者名，因此重名只在一个人名下才碍事。"""
    _upgrade(scratch, "head")

    with _connect(scratch) as connection:
        owner = uuid4().hex
        _insert_user(connection, owner)
        _insert_agent(connection, uuid4().hex, owner, name="喵语老师")
        with pytest.raises(psycopg.errors.UniqueViolation):
            _insert_agent(connection, uuid4().hex, owner, name="喵语老师")


def test_two_authors_can_use_the_same_agent_name(scratch: str) -> None:
    """全库唯一意味着谁先占了名字别人就不能用 —— 这条断言就是那个定案的守门人。"""
    _upgrade(scratch, "head")

    with _connect(scratch) as connection:
        first, second = uuid4().hex, uuid4().hex
        _insert_user(connection, first)
        _insert_user(connection, second)
        _insert_agent(connection, uuid4().hex, first, name="波动率助手")

        _insert_agent(connection, uuid4().hex, second, name="波动率助手")

        found = connection.execute("SELECT count(*) FROM agents WHERE name = '波动率助手'").fetchone()
    assert found is not None
    assert found[0] == 2


def test_deleting_an_agent_frees_its_name(scratch: str) -> None:
    """唯一索引只盖没删掉的那些。全表唯一的话，删一次名字就永久占着。"""
    _upgrade(scratch, "head")

    with _connect(scratch) as connection:
        owner = uuid4().hex
        _insert_user(connection, owner)
        _insert_agent(connection, uuid4().hex, owner, name="重名", is_deleted=True)

        _insert_agent(connection, uuid4().hex, owner, name="重名")

        found = connection.execute("SELECT count(*) FROM agents WHERE name = '重名'").fetchone()
    assert found is not None
    assert found[0] == 2


def test_an_agent_cannot_have_two_drafts(scratch: str) -> None:
    """两个草稿意味着「我在改的是哪一份」没有答案。"""
    _upgrade(scratch, "head")

    with _connect(scratch) as connection:
        owner, agent = uuid4().hex, uuid4().hex
        _insert_user(connection, owner)
        _insert_agent(connection, agent, owner)
        _insert_version(connection, uuid4().hex, agent, version=1)
        with pytest.raises(psycopg.errors.UniqueViolation):
            _insert_version(connection, uuid4().hex, agent, version=2)


def test_an_agent_keeps_every_released_version(scratch: str) -> None:
    """已发布的版本永远留着：落进 run 快照的引用要照常读得回来。"""
    _upgrade(scratch, "head")

    with _connect(scratch) as connection:
        owner, agent = uuid4().hex, uuid4().hex
        _insert_user(connection, owner)
        _insert_agent(connection, agent, owner)
        _insert_version(connection, uuid4().hex, agent, version=1, status="released")
        _insert_version(connection, uuid4().hex, agent, version=2, status="released")
        _insert_version(connection, uuid4().hex, agent, version=3)

        found = connection.execute("SELECT count(*) FROM agent_versions WHERE agent_id = %s", (agent,)).fetchone()
    assert found is not None
    assert found[0] == 3


def test_a_version_number_cannot_repeat_within_one_agent(scratch: str) -> None:
    """版本号是 run 快照里那半个引用（`agent_id@version`），重号等于快照指不准。"""
    _upgrade(scratch, "head")

    with _connect(scratch) as connection:
        owner, agent = uuid4().hex, uuid4().hex
        _insert_user(connection, owner)
        _insert_agent(connection, agent, owner)
        _insert_version(connection, uuid4().hex, agent, version=1, status="released")
        with pytest.raises(psycopg.errors.UniqueViolation):
            _insert_version(connection, uuid4().hex, agent, version=1, status="released")


def test_a_version_cannot_have_two_pending_reviews(scratch: str) -> None:
    """连点两次提审只该在 reviewer 的队列里留下一条。"""
    _upgrade(scratch, "head")

    with _connect(scratch) as connection:
        owner, agent, version = uuid4().hex, uuid4().hex, uuid4().hex
        _insert_user(connection, owner)
        _insert_agent(connection, agent, owner)
        _insert_version(connection, version, agent, status="released")
        _insert_review(connection, version, owner)
        with pytest.raises(psycopg.errors.UniqueViolation):
            _insert_review(connection, version, owner)


def test_a_rejected_version_can_be_submitted_again(scratch: str) -> None:
    """唯一约束只盖 pending 那一段：被拒之后改了再提是常态，不是异常。"""
    _upgrade(scratch, "head")

    with _connect(scratch) as connection:
        owner, agent, version = uuid4().hex, uuid4().hex, uuid4().hex
        _insert_user(connection, owner)
        _insert_agent(connection, agent, owner)
        _insert_version(connection, version, agent, status="released")
        _insert_review(connection, version, owner, status="rejected")

        _insert_review(connection, version, owner)

        found = connection.execute("SELECT count(*) FROM reviews WHERE target_id = %s", (version,)).fetchone()
    assert found is not None
    assert found[0] == 2


def test_one_agent_can_be_shared_with_several_groups(scratch: str) -> None:
    """共享是关联表而不是 `agents` 上的一列 —— 一个资源可以同时给多个组。"""
    _upgrade(scratch, "head")

    with _connect(scratch) as connection:
        owner, agent, first, second = uuid4().hex, uuid4().hex, uuid4().hex, uuid4().hex
        _insert_user(connection, owner)
        _insert_agent(connection, agent, owner)
        _insert_group(connection, first, owner, code="AAAA")
        _insert_group(connection, second, owner, code="BBBB")
        for group in (first, second):
            connection.execute(
                "INSERT INTO resource_groups (resource_kind, resource_id, group_id) VALUES ('agent', %s, %s)",
                (agent, group),
            )
        with pytest.raises(psycopg.errors.UniqueViolation):
            connection.execute(
                "INSERT INTO resource_groups (resource_kind, resource_id, group_id) VALUES ('agent', %s, %s)",
                (agent, first),
            )


def test_a_run_can_be_written_with_its_owner(scratch: str) -> None:
    """两条外键都满足时照常写得进去 —— 上面三条不能是「外键把表锁死了」。"""
    _upgrade(scratch, "head")

    user_id, thread_id, run_id = uuid4().hex, uuid4().hex, uuid4().hex
    with _connect(scratch) as connection:
        _insert_user(connection, user_id)
        _insert_thread(connection, thread_id, user_id)
        connection.execute(
            "INSERT INTO runs (id, thread_id, user_id, status,"
            " tokens_cache_read, tokens_uncached, tokens_output, started_at)"
            " VALUES (%s, %s, %s, 'queued', 0, 0, 0, %s)",
            (run_id, thread_id, user_id, datetime.now(UTC)),
        )
        found = connection.execute("SELECT user_id, agent_config FROM runs WHERE id = %s", (run_id,)).fetchone()
    assert found is not None
    assert str(found[0]).replace("-", "") == user_id
    assert found[1] is None


def _insert_skill(
    connection: psycopg.Connection[tuple[object, ...]],
    skill_id: str,
    owner_id: str,
    *,
    name: str | None = None,
    is_deleted: bool = False,
) -> None:
    now = datetime.now(UTC)
    connection.execute(
        "INSERT INTO skills (id, owner_id, name, subject, visibility, call_count,"
        " is_deleted, created_at, updated_at)"
        " VALUES (%s, %s, %s, '', 'private', 0, %s, %s, %s)",
        (skill_id, owner_id, name or f"s-{skill_id[:8]}", is_deleted, now, now),
    )


def _insert_skill_version(
    connection: psycopg.Connection[tuple[object, ...]],
    version_id: str,
    skill_id: str,
    *,
    version: int = 1,
    status: str = "draft",
) -> None:
    connection.execute(
        "INSERT INTO skill_versions"
        " (id, skill_id, version, status, description, file_count, total_bytes, created_at)"
        " VALUES (%s, %s, %s, %s, '', 1, 8, %s)",
        (version_id, skill_id, version, status, datetime.now(UTC)),
    )


def test_skill_catalog_migration_is_reversible_without_touching_agent_rows(scratch: str) -> None:
    _upgrade(scratch, BEFORE_SKILL_CATALOG)
    owner, agent, version = uuid4().hex, uuid4().hex, uuid4().hex
    with _connect(scratch) as connection:
        _insert_user(connection, owner)
        _insert_agent(connection, agent, owner)
        _insert_version(connection, version, agent)
        review_columns = _column(scratch, "reviews")
        resource_group_columns = _column(scratch, "resource_groups")

    _upgrade(scratch, "head")

    assert {"skills", "skill_versions"} <= _table(scratch)
    assert "skill_refs" in _column(scratch, "agent_versions")
    assert _column(scratch, "reviews") == review_columns
    assert _column(scratch, "resource_groups") == resource_group_columns
    with _connect(scratch) as connection:
        found = connection.execute("SELECT skill_refs FROM agent_versions WHERE id = %s", (version,)).fetchone()
    assert found == (None,)

    _downgrade(scratch, BEFORE_SKILL_CATALOG)

    assert not {"skills", "skill_versions"} & _table(scratch)
    assert "skill_refs" not in _column(scratch, "agent_versions")
    with _connect(scratch) as connection:
        assert connection.execute("SELECT 1 FROM agent_versions WHERE id = %s", (version,)).fetchone() is not None


def test_one_author_cannot_use_the_same_active_skill_name_twice(scratch: str) -> None:
    _upgrade(scratch, "head")

    with _connect(scratch) as connection:
        owner = uuid4().hex
        _insert_user(connection, owner)
        _insert_skill(connection, uuid4().hex, owner, name="annualized-naming")
        with pytest.raises(psycopg.errors.UniqueViolation):
            _insert_skill(connection, uuid4().hex, owner, name="annualized-naming")


def test_deleting_a_skill_frees_its_name(scratch: str) -> None:
    _upgrade(scratch, "head")

    with _connect(scratch) as connection:
        owner = uuid4().hex
        _insert_user(connection, owner)
        _insert_skill(connection, uuid4().hex, owner, name="annualized-naming", is_deleted=True)
        _insert_skill(connection, uuid4().hex, owner, name="annualized-naming")

        found = connection.execute(
            "SELECT count(*) FROM skills WHERE owner_id = %s AND name = 'annualized-naming'", (owner,)
        ).fetchone()
    assert found is not None
    assert found[0] == 2


def test_one_skill_cannot_have_two_drafts(scratch: str) -> None:
    _upgrade(scratch, "head")

    with _connect(scratch) as connection:
        owner, skill = uuid4().hex, uuid4().hex
        _insert_user(connection, owner)
        _insert_skill(connection, skill, owner)
        _insert_skill_version(connection, uuid4().hex, skill)
        with pytest.raises(psycopg.errors.UniqueViolation):
            _insert_skill_version(connection, uuid4().hex, skill, version=2)

        _insert_skill_version(connection, uuid4().hex, skill, version=2, status="released")


def test_a_skill_version_number_cannot_repeat(scratch: str) -> None:
    _upgrade(scratch, "head")

    with _connect(scratch) as connection:
        owner, skill = uuid4().hex, uuid4().hex
        _insert_user(connection, owner)
        _insert_skill(connection, skill, owner)
        _insert_skill_version(connection, uuid4().hex, skill, status="released")
        with pytest.raises(psycopg.errors.UniqueViolation):
            _insert_skill_version(connection, uuid4().hex, skill, status="released")


def test_shared_and_reviewed_resources_accept_skill_kind(scratch: str) -> None:
    _upgrade(scratch, "head")

    with _connect(scratch) as connection:
        owner, skill, version, group = uuid4().hex, uuid4().hex, uuid4().hex, uuid4().hex
        _insert_user(connection, owner)
        _insert_group(connection, group, owner)
        _insert_skill(connection, skill, owner)
        _insert_skill_version(connection, version, skill, status="released")
        connection.execute(
            "INSERT INTO resource_groups (resource_kind, resource_id, group_id) VALUES ('skill', %s, %s)",
            (skill, group),
        )
        connection.execute(
            "INSERT INTO reviews (id, target_kind, target_id, status, responsibility_confirmed,"
            " submitted_by, created_at) VALUES (%s, 'skill', %s, 'pending', true, %s, %s)",
            (uuid4().hex, version, owner, datetime.now(UTC)),
        )

        shared = connection.execute(
            "SELECT count(*) FROM resource_groups WHERE resource_kind = 'skill' AND resource_id = %s", (skill,)
        ).fetchone()
        reviewed = connection.execute(
            "SELECT count(*) FROM reviews WHERE target_kind = 'skill' AND target_id = %s", (version,)
        ).fetchone()
    assert shared == (1,)
    assert reviewed == (1,)
