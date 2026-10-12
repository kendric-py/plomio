"""add direct_requests table (history of direct requests)

Revision ID: f1a6c3d8b972
Revises: e8c4a7d12f63
Create Date: 2026-10-12 21:00:00.000000

Журнал direct-запросов: метаданные каждого запроса (итог, тайминги, прокси, списание), без
результата. Срок хранения не ограничен.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f1a6c3d8b972'
down_revision: Union[str, None] = 'e8c4a7d12f63'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'direct_requests',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('request_id', sa.String(), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column(
            'marketplace',
            postgresql.ENUM('OZON', 'WILDBERRIES', name='marketplace', create_type=False),
            nullable=False,
        ),
        sa.Column(
            'request_type',
            sa.Enum(
                'PRODUCT_PAGE', 'REVIEWS', 'SEARCH', 'CATEGORY', 'SELLER', name='directrequesttype',
            ),
            nullable=False,
        ),
        sa.Column(
            'outcome',
            sa.Enum(
                'OK', 'INVALID_INPUT', 'NOT_FOUND', 'UNAVAILABLE', 'ERROR', 'TIMEOUT',
                'BILLING_FAILED', name='directoutcome',
            ),
            nullable=False,
        ),
        sa.Column('http_status', sa.SmallInteger(), nullable=False),
        sa.Column('input_value', sa.String(), nullable=False),
        sa.Column('is_next_page', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('items_count', sa.Integer(), nullable=True),
        sa.Column('has_next_page', sa.Boolean(), nullable=True),
        sa.Column('credits_charged', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('proxy_id', sa.Integer(), sa.ForeignKey('proxies.id', ondelete='SET NULL'), nullable=True),
        sa.Column('total_ms', sa.Integer(), nullable=False),
        sa.Column('attempts', sa.SmallInteger(), nullable=True),
        sa.Column('queue_ms', sa.Integer(), nullable=True),
        sa.Column('session_ms', sa.Integer(), nullable=True),
        sa.Column('fetch_ms', sa.Integer(), nullable=True),
        sa.Column('worker_ms', sa.Integer(), nullable=True),
        sa.Column('error_detail', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('request_id', name='uq_direct_requests_request_id'),
    )
    op.create_index('ix_direct_requests_created_at', 'direct_requests', ['created_at'])
    op.create_index('ix_direct_requests_user_created', 'direct_requests', ['user_id', 'created_at'])
    op.create_index('ix_direct_requests_marketplace_created', 'direct_requests', ['marketplace', 'created_at'])
    op.create_index('ix_direct_requests_outcome_created', 'direct_requests', ['outcome', 'created_at'])


def downgrade() -> None:
    op.drop_index('ix_direct_requests_outcome_created', table_name='direct_requests')
    op.drop_index('ix_direct_requests_marketplace_created', table_name='direct_requests')
    op.drop_index('ix_direct_requests_user_created', table_name='direct_requests')
    op.drop_index('ix_direct_requests_created_at', table_name='direct_requests')
    op.drop_table('direct_requests')
    op.execute('DROP TYPE directoutcome')
    op.execute('DROP TYPE directrequesttype')
