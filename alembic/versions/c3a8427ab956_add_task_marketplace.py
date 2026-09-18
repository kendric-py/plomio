"""add task marketplace

Revision ID: c3a8427ab956
Revises: 2f95c8d07362
Create Date: 2026-09-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c3a8427ab956'
down_revision: Union[str, None] = '2f95c8d07362'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    marketplace_enum = sa.Enum('OZON', 'WILDBERRIES', name='marketplace')
    marketplace_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        'tasks',
        sa.Column(
            'marketplace',
            sa.Enum('OZON', 'WILDBERRIES', name='marketplace', create_type=False),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column('tasks', 'marketplace')
    sa.Enum(name='marketplace').drop(op.get_bind(), checkfirst=True)
