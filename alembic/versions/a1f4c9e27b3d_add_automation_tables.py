"""add automation tables

Revision ID: a1f4c9e27b3d
Revises: 9b3d4e7a1c2f
Create Date: 2026-09-21 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a1f4c9e27b3d'
down_revision: Union[str, None] = '9b3d4e7a1c2f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('automations',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('marketplace', postgresql.ENUM('OZON', 'WILDBERRIES', name='marketplace', create_type=False), nullable=False),
    sa.Column('input_value', sa.String(), nullable=False),
    sa.Column('status', sa.Enum('ACTIVE', 'PAUSED', name='automationstatus'), server_default='ACTIVE', nullable=False),
    sa.Column('price_drop_threshold_percent', sa.Integer(), nullable=False),
    sa.Column('check_frequency_minutes', sa.Integer(), nullable=False),
    sa.Column('history_retention_days', sa.Integer(), nullable=False),
    sa.Column('baseline_price_kopecks', sa.Integer(), nullable=True),
    sa.Column('baseline_discounted_price_kopecks', sa.Integer(), nullable=True),
    sa.Column('baseline_original_price_kopecks', sa.Integer(), nullable=True),
    sa.Column('next_check_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('pending_task_id', sa.UUID(), nullable=True),
    sa.Column('last_checked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_check_error', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('price_drop_threshold_percent BETWEEN 1 AND 100', name='ck_automations_price_drop_threshold_range'),
    sa.ForeignKeyConstraint(['pending_task_id'], ['tasks.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_automations_status_next_check_at', 'automations', ['status', 'next_check_at'],
    )
    op.create_index(
        'ix_automations_pending_task_id', 'automations', ['pending_task_id'],
    )

    op.create_table('automation_history',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('automation_id', sa.UUID(), nullable=False),
    sa.Column('changes', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('threshold_breached', sa.Boolean(), nullable=False),
    sa.Column('detected_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['automation_id'], ['automations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_automation_history_automation_id_detected_at',
        'automation_history',
        ['automation_id', 'detected_at'],
    )


def downgrade() -> None:
    op.drop_index('ix_automation_history_automation_id_detected_at', table_name='automation_history')
    op.drop_table('automation_history')
    op.drop_index('ix_automations_pending_task_id', table_name='automations')
    op.drop_index('ix_automations_status_next_check_at', table_name='automations')
    op.drop_table('automations')
    sa.Enum(name='automationstatus').drop(op.get_bind(), checkfirst=True)
