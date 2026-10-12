"""add proxy_generation_failures table and PROXY_FAILURE_RETENTION_SWEEP cron job

Revision ID: d5b9f2c81e47
Revises: a7d3e9b15c28
Create Date: 2026-10-12 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd5b9f2c81e47'
down_revision: Union[str, None] = 'a7d3e9b15c28'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('proxy_generation_failures',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('proxy_id', sa.Integer(), nullable=False),
    sa.Column('marketplace', postgresql.ENUM('OZON', 'WILDBERRIES', name='marketplace', create_type=False), nullable=False),
    sa.Column('error_kind', sa.Enum('ANTIBOT_INIT', 'VALIDATION', 'PROXY_UNAVAILABLE', 'OTHER', name='proxyfailurekind'), nullable=False),
    sa.Column('traceback', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['proxy_id'], ['proxies.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_proxy_generation_failures_proxy_created', 'proxy_generation_failures', ['proxy_id', 'created_at'], unique=False)
    op.create_index('ix_proxy_generation_failures_marketplace_created', 'proxy_generation_failures', ['marketplace', 'created_at'], unique=False)
    op.execute("ALTER TYPE cronjobname ADD VALUE IF NOT EXISTS 'PROXY_FAILURE_RETENTION_SWEEP'")


def downgrade() -> None:
    op.drop_index('ix_proxy_generation_failures_marketplace_created', table_name='proxy_generation_failures')
    op.drop_index('ix_proxy_generation_failures_proxy_created', table_name='proxy_generation_failures')
    op.drop_table('proxy_generation_failures')
    op.execute('DROP TYPE IF EXISTS proxyfailurekind')
    # Значение enum `cronjobname` не удаляется — конвенция репозитория (см. b7e2d81f4a9c).
