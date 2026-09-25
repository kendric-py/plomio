"""rename automation_history to automation_check_log

Revision ID: b4e8f2a91c6d
Revises: d3f6b2c8a175
Create Date: 2026-09-25 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b4e8f2a91c6d'
down_revision: Union[str, None] = 'd3f6b2c8a175'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.rename_table('automation_history', 'automation_check_log')
    op.alter_column('automation_check_log', 'detected_at', new_column_name='checked_at')
    op.execute(
        'ALTER INDEX ix_automation_history_automation_id_detected_at '
        'RENAME TO ix_automation_check_log_automation_id_checked_at',
    )


def downgrade() -> None:
    op.execute(
        'ALTER INDEX ix_automation_check_log_automation_id_checked_at '
        'RENAME TO ix_automation_history_automation_id_detected_at',
    )
    op.alter_column('automation_check_log', 'checked_at', new_column_name='detected_at')
    op.rename_table('automation_check_log', 'automation_history')
