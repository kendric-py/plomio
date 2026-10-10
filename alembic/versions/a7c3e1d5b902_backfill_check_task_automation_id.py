"""backfill automation_id in credit transaction metadata for check tasks

Расход на автоматизацию считается по `transaction_metadata.automation_id` у списаний проверочных
задач. Новые списания пишут его сами (`TaskService.record_item_progress`), этот скрипт проставляет
его старым строкам по связи задача → автоматизация.

Revision ID: a7c3e1d5b902
Revises: d7a1c3e5b902
Create Date: 2026-10-09 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a7c3e1d5b902'
down_revision: Union[str, None] = 'd7a1c3e5b902'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE credit_transactions AS ct
        SET transaction_metadata = ct.transaction_metadata
            || jsonb_build_object('automation_id', t.automation_id::text)
        FROM tasks AS t
        WHERE ct.reference_type = 'TASK'
          AND ct.reference_id = t.id::text
          AND t.automation_id IS NOT NULL
          AND ct.transaction_metadata IS NOT NULL
          AND NOT (ct.transaction_metadata ? 'automation_id')
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE credit_transactions
        SET transaction_metadata = transaction_metadata - 'automation_id'
        WHERE transaction_metadata ? 'automation_id'
        """
    )
