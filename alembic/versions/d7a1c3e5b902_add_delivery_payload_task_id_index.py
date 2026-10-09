"""add notification_deliveries payload task_id index

Revision ID: d7a1c3e5b902
Revises: c4e8a1d7f295
Create Date: 2026-10-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd7a1c3e5b902'
down_revision: Union[str, None] = 'c4e8a1d7f295'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Админка находит доставки задачи по payload.task_id (task.* и automation.change_detected).
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_notification_deliveries_payload_task_id "
        "ON notification_deliveries ((payload->>'task_id'))"
    )
    # И история уведомлений автоматизации — по payload.automation_id.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_notification_deliveries_payload_automation_id "
        "ON notification_deliveries ((payload->>'automation_id'))"
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS ix_notification_deliveries_payload_automation_id')
    op.execute('DROP INDEX IF EXISTS ix_notification_deliveries_payload_task_id')
