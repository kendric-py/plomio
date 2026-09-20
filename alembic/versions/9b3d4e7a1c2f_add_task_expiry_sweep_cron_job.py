"""add TASK_EXPIRY_SWEEP value to cronjobname enum

Revision ID: 9b3d4e7a1c2f
Revises: 7a1f2c9d4e6b
Create Date: 2026-09-20 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '9b3d4e7a1c2f'
down_revision: Union[str, None] = '7a1f2c9d4e6b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE cronjobname ADD VALUE IF NOT EXISTS 'TASK_EXPIRY_SWEEP'")


def downgrade() -> None:
    # Postgres doesn't support removing a value from an enum type; downgrading would require
    # recreating the type and rewriting every dependent column, which isn't worth it for a
    # cron job label. Left as a no-op, matching this repo's convention for enum-value additions.
    pass
