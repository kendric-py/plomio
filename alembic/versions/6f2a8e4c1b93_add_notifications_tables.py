"""add notifications tables

Revision ID: 6f2a8e4c1b93
Revises: 1d9c5f3e8a72
Create Date: 2026-09-25 09:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '6f2a8e4c1b93'
down_revision: Union[str, None] = '1d9c5f3e8a72'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('notification_events',
    sa.Column('event_code', sa.String(), nullable=False),
    sa.Column('description', sa.String(), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('available_fields', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.PrimaryKeyConstraint('event_code'),
    )

    op.create_table('notification_settings',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('preferences', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id'),
    )

    op.create_table('notification_deliveries',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('event_code', sa.String(), nullable=False),
    sa.Column('channel', sa.Enum('TELEGRAM', name='notificationchannel'), nullable=False),
    sa.Column(
        'status',
        sa.Enum('PENDING', 'SENT', 'FAILED', name='notificationdeliverystatus'),
        server_default='PENDING',
        nullable=False,
    ),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('failure_reason', sa.String(), nullable=True),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['event_code'], ['notification_events.event_code'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_notification_deliveries_status_created_at',
        'notification_deliveries',
        ['status', 'created_at'],
    )
    op.create_index(
        'ix_notification_deliveries_user_id',
        'notification_deliveries',
        ['user_id'],
    )

    notification_events_table = sa.table(
        'notification_events',
        sa.column('event_code', sa.String()),
        sa.column('description', sa.String()),
        sa.column('is_active', sa.Boolean()),
        sa.column('available_fields', postgresql.JSONB(astext_type=sa.Text())),
    )
    op.bulk_insert(
        notification_events_table,
        [
            {
                'event_code': 'automation.change_detected',
                'description': (
                    'Автоматизация завершила тик проверки с изменением карточки товара и/или '
                    'пробитием порога падения цены'
                ),
                'is_active': True,
                'available_fields': [
                    'PRICE', 'DISCOUNTED_PRICE', 'ORIGINAL_PRICE', 'IN_STOCK',
                    'TITLE', 'RATING', 'REVIEW_COUNT', 'SELLER_NAME',
                ],
            },
            {
                'event_code': 'task.completed',
                'description': 'Задача парсинга успешно завершена',
                'is_active': True,
                'available_fields': None,
            },
            {
                'event_code': 'task.failed',
                'description': 'Задача парсинга завершена с ошибкой',
                'is_active': True,
                'available_fields': None,
            },
        ],
    )


def downgrade() -> None:
    op.drop_index('ix_notification_deliveries_user_id', table_name='notification_deliveries')
    op.drop_index('ix_notification_deliveries_status_created_at', table_name='notification_deliveries')
    op.drop_table('notification_deliveries')
    op.drop_table('notification_settings')
    op.drop_table('notification_events')
    sa.Enum(name='notificationdeliverystatus').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='notificationchannel').drop(op.get_bind(), checkfirst=True)
