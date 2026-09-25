"""add automation check log tick columns

Revision ID: 1d9c5f3e8a72
Revises: b4e8f2a91c6d
Create Date: 2026-09-25 09:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '1d9c5f3e8a72'
down_revision: Union[str, None] = 'b4e8f2a91c6d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default backfills existing rows: every AutomationHistory row that already exists was,
    # by the old write rule, a successful check with a real change — succeeded=true/has_changes=true
    # is the correct historical value for them.
    op.add_column(
        'automation_check_log',
        sa.Column('succeeded', sa.Boolean(), server_default='true', nullable=False),
    )
    op.add_column('automation_check_log', sa.Column('error_message', sa.String(), nullable=True))
    op.add_column(
        'automation_check_log',
        sa.Column('snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        'automation_check_log',
        sa.Column('has_changes', sa.Boolean(), server_default='true', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('automation_check_log', 'has_changes')
    op.drop_column('automation_check_log', 'snapshot')
    op.drop_column('automation_check_log', 'error_message')
    op.drop_column('automation_check_log', 'succeeded')
