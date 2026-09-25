"""add task pricing_dimension_code/value

Revision ID: d3f6b2c8a175
Revises: c8a1f4b9e6d3
Create Date: 2026-09-24 10:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd3f6b2c8a175'
down_revision: Union[str, None] = 'c8a1f4b9e6d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('tasks', sa.Column('pricing_dimension_code', sa.String(), nullable=True))
    op.add_column('tasks', sa.Column('pricing_dimension_value', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('tasks', 'pricing_dimension_value')
    op.drop_column('tasks', 'pricing_dimension_code')
