"""add automation in_stock

Revision ID: f2b6a9d13c47
Revises: e91a3c5f7b02
Create Date: 2026-09-22 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f2b6a9d13c47'
down_revision: Union[str, None] = 'e91a3c5f7b02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('automations', sa.Column('in_stock', sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column('automations', 'in_stock')
