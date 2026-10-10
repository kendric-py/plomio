"""add spending limits and billing notification events

Revision ID: b8e2d4f61a37
Revises: a7c3e1d5b902
Create Date: 2026-10-09 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b8e2d4f61a37'
down_revision: Union[str, None] = 'a7c3e1d5b902'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_EVENTS = [
    {
        'event_code': 'task.paused_insufficient_credits',
        'description': 'Задача приостановлена: закончились кредиты или достигнут лимит расходов',
        'is_active': True,
        'available_fields': None,
    },
    {
        'event_code': 'billing.balance_depleted',
        'description': 'Баланс кредитов исчерпан',
        'is_active': True,
        'available_fields': None,
    },
    {
        'event_code': 'billing.balance_low',
        'description': 'Кредитов осталось мало (баланс упал ниже порога)',
        'is_active': True,
        'available_fields': None,
    },
]


def upgrade() -> None:
    op.create_table(
        'spending_limits',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('daily_limit', sa.Integer(), nullable=True),
        sa.Column('monthly_limit', sa.Integer(), nullable=True),
        sa.Column(
            'updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id'),
    )

    notification_events = sa.table(
        'notification_events',
        sa.column('event_code', sa.String()),
        sa.column('description', sa.String()),
        sa.column('is_active', sa.Boolean()),
        sa.column('available_fields', sa.JSON()),
    )
    op.bulk_insert(notification_events, NEW_EVENTS)


def downgrade() -> None:
    codes = ', '.join(f"'{event['event_code']}'" for event in NEW_EVENTS)
    # notification_deliveries ссылается на каталог с ON DELETE CASCADE — доставки этих событий уйдут вместе с ними.
    op.execute(f'DELETE FROM notification_events WHERE event_code IN ({codes})')
    op.drop_table('spending_limits')
