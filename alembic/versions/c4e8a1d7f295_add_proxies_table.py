"""add proxies table

Revision ID: c4e8a1d7f295
Revises: b9d3e7a25c18
Create Date: 2026-10-01 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c4e8a1d7f295'
down_revision: Union[str, None] = 'b9d3e7a25c18'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('proxies',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('proxy_type', sa.Enum('HTTP', 'SOCKS5', name='proxytype'), nullable=False),
    sa.Column('host', sa.String(), nullable=False),
    sa.Column('port', sa.Integer(), nullable=False),
    sa.Column('username', sa.String(), nullable=True),
    sa.Column('password', sa.String(), nullable=True),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('note', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('proxy_type', 'host', 'port', 'username', name='uq_proxies_endpoint', postgresql_nulls_not_distinct=True)
    )


def downgrade() -> None:
    op.drop_table('proxies')
    op.execute('DROP TYPE IF EXISTS proxytype')
