"""add task started_at/finished_at

Revision ID: a3d7c69e5f21
Revises: f2b6a9d13c47
Create Date: 2026-09-23 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a3d7c69e5f21'
down_revision: Union[str, None] = 'f2b6a9d13c47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('tasks', sa.Column('started_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('tasks', sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('tasks', 'finished_at')
    op.drop_column('tasks', 'started_at')
