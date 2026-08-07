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

# 本期新建的两张表加上 P2 那两张。downgrade 之后一张都不该剩
PLATFORM_TABLE = ("users", "threads", "runs", "run_events")

# 补外键之前的那一版。已有的 runs 行就是在这一版上写下的
BEFORE_USER_MODEL = "0002_run_events"


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


def _insert_user(connection: psycopg.Connection[tuple[object, ...]], user_id: str) -> None:
    connection.execute(
        "INSERT INTO users (id, name, password_hash, role, is_active, created_at)"
        " VALUES (%s, %s, 'x', 'teacher', true, %s)",
        (user_id, f"u-{user_id[:8]}", datetime.now(UTC)),
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


def test_a_run_still_takes_a_thread_that_has_no_row(scratch: str) -> None:
    """这一版**故意**不约束 `runs.thread_id`。

    `threads` 表此刻还是空的，而提交 run 的入口仍只建目录不落表 —— 现在加外键，
    每一次提交都会当场炸在插入上。这条用例会随隔离那一步落地而改成它的反面，
    那时 api 已经先落 `threads` 行，外键才约束得住真实的写入路径。
    """
    _upgrade(scratch, "head")

    with _connect(scratch) as connection:
        _insert_run(connection, uuid4().hex, uuid4().hex)


def test_a_thread_must_point_at_an_existing_user(scratch: str) -> None:
    _upgrade(scratch, "head")

    with _connect(scratch) as connection, pytest.raises(psycopg.errors.ForeignKeyViolation):
        _insert_thread(connection, uuid4().hex, uuid4().hex)


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
        found = connection.execute("SELECT user_id FROM runs WHERE id = %s", (run_id,)).fetchone()
    assert found is not None
    assert str(found[0]).replace("-", "") == user_id
