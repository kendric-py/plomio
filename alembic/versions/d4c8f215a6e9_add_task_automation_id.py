"""add task automation_id

Revision ID: d4c8f215a6e9
Revises: b7e2d81f4a9c
Create Date: 2026-09-22 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd4c8f215a6e9'
down_revision: Union[str, None] = 'b7e2d81f4a9c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'tasks',
        sa.Column('automation_id', sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        'fk_tasks_automation_id_automations',
        'tasks',
        'automations',
        ['automation_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_tasks_automation_id_automations', 'tasks', type_='foreignkey')
    op.drop_column('tasks', 'automation_id')
