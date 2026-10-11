"""add system.sessions_depleted notification event and SESSION_POOL_ALERT cron job

Revision ID: c4f8a1d7e2b9
Revises: b8e2d4f61a37
Create Date: 2026-10-11 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c4f8a1d7e2b9'
down_revision: Union[str, None] = 'b8e2d4f61a37'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EVENT = {
    'event_code': 'system.sessions_depleted',
    'description': 'В пуле нет сессий по маркетплейсу (только для администраторов)',
    'is_active': True,
    'available_fields': None,
}


def upgrade() -> None:
    op.execute("ALTER TYPE cronjobname ADD VALUE IF NOT EXISTS 'SESSION_POOL_ALERT'")
    notification_events = sa.table(
        'notification_events',
        sa.column('event_code', sa.String()),
        sa.column('description', sa.String()),
        sa.column('is_active', sa.Boolean()),
        sa.column('available_fields', sa.JSON()),
    )
    op.bulk_insert(notification_events, [EVENT])


def downgrade() -> None:
    # Значение enum cronjobname Postgres удалить не умеет — оставляем, как в остальных миграциях.
    op.execute("DELETE FROM notification_events WHERE event_code = 'system.sessions_depleted'")
