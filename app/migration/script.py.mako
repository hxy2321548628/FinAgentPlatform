"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""

import sqlalchemy as sa

from alembic import op
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: str | None = ${repr(down_revision)}
branch_labels: str | None = ${repr(branch_labels)}
depends_on: str | None = ${repr(depends_on)}


def upgrade() -> None:
    """建表 / 改表。"""
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """回滚上面那一步。"""
    ${downgrades if downgrades else "pass"}
