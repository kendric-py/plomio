"""add billing tables

Revision ID: c8a1f4b9e6d3
Revises: a3d7c69e5f21
Create Date: 2026-09-24 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c8a1f4b9e6d3'
down_revision: Union[str, None] = 'a3d7c69e5f21'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('billing_actions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('action_code', sa.String(), nullable=False),
    sa.Column('description', sa.String(), nullable=False),
    sa.Column('base_cost', sa.Integer(), server_default='0', nullable=False),
    sa.Column('unit_label', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('action_code', name='uq_billing_actions_action_code'),
    )

    op.create_table('pricing_multiplier_rules',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('dimension_code', sa.String(), nullable=False),
    sa.Column('value_min', sa.Integer(), nullable=False),
    sa.Column('value_max', sa.Integer(), nullable=False),
    sa.Column('multiplier', sa.Numeric(5, 2), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_pricing_multiplier_rules_dimension_code',
        'pricing_multiplier_rules',
        ['dimension_code'],
    )

    op.create_table('credit_wallets',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('balance', sa.Integer(), server_default='0', nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id'),
    )

    op.create_table('credit_transactions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('amount', sa.Integer(), nullable=False),
    sa.Column('balance_after', sa.Integer(), nullable=False),
    sa.Column('action_code', sa.String(), nullable=True),
    sa.Column('reference_type', sa.Enum('TASK', 'AUTOMATION', name='referencetype'), nullable=True),
    sa.Column('reference_id', sa.String(), nullable=True),
    sa.Column('transaction_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('granted_by_admin_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['action_code'], ['billing_actions.action_code'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['granted_by_admin_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_credit_transactions_user_id_created_at',
        'credit_transactions',
        ['user_id', 'created_at'],
    )

    billing_actions_table = sa.table(
        'billing_actions',
        sa.column('action_code', sa.String()),
        sa.column('description', sa.String()),
        sa.column('base_cost', sa.Integer()),
        sa.column('unit_label', sa.String()),
    )
    op.bulk_insert(
        billing_actions_table,
        [
            {
                'action_code': 'task.create',
                'description': 'Создание разовой задачи парсинга',
                'base_cost': 0,
                'unit_label': 'действие',
            },
            {
                'action_code': 'automation.create',
                'description': 'Создание автоматизации мониторинга цены',
                'base_cost': 0,
                'unit_label': 'действие',
            },
            {
                'action_code': 'result.PRODUCT_PAGE',
                'description': 'Результат парсинга карточки товара',
                'base_cost': 1,
                'unit_label': 'результат',
            },
            {
                'action_code': 'result.SEARCH_QUERY',
                'description': 'Результат парсинга поисковой выдачи',
                'base_cost': 0,
                'unit_label': 'результат',
            },
            {
                'action_code': 'result.REVIEWS',
                'description': 'Результат парсинга отзыва',
                'base_cost': 0,
                'unit_label': 'результат',
            },
            {
                'action_code': 'result.CATEGORY',
                'description': 'Результат парсинга категории',
                'base_cost': 0,
                'unit_label': 'результат',
            },
            {
                'action_code': 'result.SELLER',
                'description': 'Результат парсинга профиля/каталога продавца',
                'base_cost': 0,
                'unit_label': 'результат',
            },
        ],
    )


def downgrade() -> None:
    op.drop_index('ix_credit_transactions_user_id_created_at', table_name='credit_transactions')
    op.drop_table('credit_transactions')
    op.drop_table('credit_wallets')
    op.drop_index('ix_pricing_multiplier_rules_dimension_code', table_name='pricing_multiplier_rules')
    op.drop_table('pricing_multiplier_rules')
    op.drop_table('billing_actions')
    sa.Enum(name='referencetype').drop(op.get_bind(), checkfirst=True)
