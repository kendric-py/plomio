"""add system.sessions_restored notification event

Revision ID: a7d3e9b15c28
Revises: c4f8a1d7e2b9
Create Date: 2026-10-12 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a7d3e9b15c28'
down_revision: Union[str, None] = 'c4f8a1d7e2b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EVENT = {
    'event_code': 'system.sessions_restored',
    'description': 'В пуле снова появились сессии по маркетплейсу (только для администраторов)',
    'is_active': True,
    'available_fields': None,
}


def upgrade() -> None:
    notification_events = sa.table(
        'notification_events',
        sa.column('event_code', sa.String()),
        sa.column('description', sa.String()),
        sa.column('is_active', sa.Boolean()),
        sa.column('available_fields', sa.JSON()),
    )
    op.bulk_insert(notification_events, [EVENT])


def downgrade() -> None:
    op.execute("DELETE FROM notification_events WHERE event_code = 'system.sessions_restored'")
