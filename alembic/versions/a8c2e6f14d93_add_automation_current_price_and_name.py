"""add automation name and current prices

Revision ID: a8c2e6f14d93
Revises: e5b2a8d4f631
Create Date: 2026-09-30 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a8c2e6f14d93'
down_revision: Union[str, None] = 'e5b2a8d4f631'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('automations', sa.Column('name', sa.String(), nullable=True))
    op.add_column('automations', sa.Column('price_kopecks', sa.Integer(), nullable=True))
    op.add_column('automations', sa.Column('discounted_price_kopecks', sa.Integer(), nullable=True))
    op.add_column('automations', sa.Column('original_price_kopecks', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('automations', 'original_price_kopecks')
    op.drop_column('automations', 'discounted_price_kopecks')
    op.drop_column('automations', 'price_kopecks')
    op.drop_column('automations', 'name')
