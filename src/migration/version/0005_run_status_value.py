"""把 runs.status 从枚举名改回枚举值

Revision ID: 0005_run_status_value
Revises: 0004_run_thread_fk
Create Date: 2026-08-08

**这是在补一个 P2 就埋下的错。** SQLModel 默认把枚举**按名字**存，于是库里躺着的是
`SUCCEEDED`，而事件契约、架构文档、以及 0001 建的那条部分索引写的都是 `succeeded`。

它不是正确性 bug —— 查询用的是同一套编码，绑定参数与列里的值始终对得上。坏掉的是
两件不出声的事：

1. `ix_runs_unfinished` 的谓词是 `status IN ('queued','running')`，**永远匹配不上任何行**，
   于是崩溃恢复那条扫描静默退化成全表扫，且会随历史 run 越来越慢；
2. 任何照文档写的 SQL（验收脚本、排障时手敲的查询）都查不到东西，而且不报错。

改法是两半：列的声明改成按值存（`run/repository.py` 的 `_value_column`），
已有的行在这里就地小写。`error_code` 那一列不用动 —— 它的名字与值本来就相同。
"""

from alembic import op

revision: str = "0005_run_status_value"
down_revision: str | None = "0004_run_thread_fk"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """建表 / 改表。"""
    op.execute("UPDATE runs SET status = lower(status) WHERE status <> lower(status)")


def downgrade() -> None:
    """回滚上面那一步。

    退回按名字存。**`cancelled` 也会被大写**：这一版之后才有这个状态，
    退到上一版时那些行照样得能被旧代码读出来。
    """
    op.execute("UPDATE runs SET status = upper(status) WHERE status <> upper(status)")
