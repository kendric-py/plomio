"""add automation cron job names to cronjobname enum

Revision ID: b7e2d81f4a9c
Revises: a1f4c9e27b3d
Create Date: 2026-09-21 10:05:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b7e2d81f4a9c'
down_revision: Union[str, None] = 'a1f4c9e27b3d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE cronjobname ADD VALUE IF NOT EXISTS 'AUTOMATION_DISPATCH'")
    op.execute("ALTER TYPE cronjobname ADD VALUE IF NOT EXISTS 'AUTOMATION_RESULT_SWEEP'")
    op.execute(
        "ALTER TYPE cronjobname ADD VALUE IF NOT EXISTS 'AUTOMATION_HISTORY_RETENTION_SWEEP'",
    )


def downgrade() -> None:
    # Postgres doesn't support removing a value from an enum type; downgrading would require
    # recreating the type and rewriting every dependent column, which isn't worth it for a
    # cron job label. Left as a no-op, matching this repo's convention for enum-value additions.
    pass
