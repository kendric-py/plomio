"""add NOTIFICATION_DELIVERY_SWEEP value to cronjobname enum

Revision ID: d92a7c3e5f18
Revises: c1e4f6a92b57
Create Date: 2026-09-28 01:10:01.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd92a7c3e5f18'
down_revision: Union[str, None] = 'c1e4f6a92b57'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE cronjobname ADD VALUE IF NOT EXISTS 'NOTIFICATION_DELIVERY_SWEEP'")


def downgrade() -> None:
    # Postgres doesn't support removing a value from an enum type; downgrading would require
    # recreating the type and rewriting every dependent column, which isn't worth it for a
    # cron job label. Left as a no-op, matching this repo's convention for enum-value additions.
    pass
