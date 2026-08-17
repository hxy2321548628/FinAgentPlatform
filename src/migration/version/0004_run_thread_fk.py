"""给 runs.thread_id 补上外键

Revision ID: 0004_run_thread_fk
Revises: 0003_user_thread
Create Date: 2026-08-08

这条外键本该跟 0003 一起加，**推到这一版是因为它约束不住任何东西**：0003 建表那一刻
`threads` 还是空的，而提交 run 的入口仍只建目录不落表 —— 外键一加，每一次提交都当场
炸在插入上。到了这一版，api 已经先落 `threads` 行再建目录，外键才真正长在写入路径上。

**NOT VALID**：0003 之前的那批 run 行指向的会话在 `threads` 表里并不存在（它们是验收
脚本跑出来的，没有真实归属，定案不回填）。普通外键会在校验历史行时直接失败。
NOT VALID 的语义正是「从现在起的写入都要合规，历史行不追究」。清完孤儿行之后可以
`ALTER TABLE runs VALIDATE CONSTRAINT fk_runs_thread` 补上校验，不必改这一版。
"""

from alembic import op

revision: str = "0004_run_thread_fk"
down_revision: str | None = "0003_user_thread"
branch_labels: str | None = None
depends_on: str | None = None

RUN_THREAD_FOREIGN_KEY = "fk_runs_thread"


def upgrade() -> None:
    """建表 / 改表。"""
    op.execute(
        f"ALTER TABLE runs ADD CONSTRAINT {RUN_THREAD_FOREIGN_KEY} "
        "FOREIGN KEY (thread_id) REFERENCES threads (id) NOT VALID"
    )


def downgrade() -> None:
    """回滚上面那一步。"""
    op.drop_constraint(RUN_THREAD_FOREIGN_KEY, "runs", type_="foreignkey")
