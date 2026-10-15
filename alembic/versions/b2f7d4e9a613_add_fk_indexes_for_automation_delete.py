"""add indexes on FK columns used by automation/task delete cascades

Revision ID: b2f7d4e9a613
Revises: c4e8a2f6b913
Create Date: 2026-10-15 12:00:00.000000

Postgres не индексирует ссылающуюся сторону FK сам. Без этих индексов каскады при удалении
автоматизации (`AutomationService.delete_automation`) сканируют таблицы целиком:

- `result_items.task_item_id` — `ON DELETE CASCADE` от `task_items`: полный скан `result_items` на
  каждый удаляемый `task_item` (основная причина многосекундного удаления автоматизации);
- `tasks.automation_id` — фильтр `TaskRepository.delete_by_automation_id` и `SET NULL` от
  `automations`;
- `automations.pending_task_id` — `SET NULL` от `tasks` на каждую удаляемую задачу.

Индексы строятся `CONCURRENTLY` (вне транзакции миграции), чтобы не блокировать запись в таблицы.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b2f7d4e9a613'
down_revision: Union[str, None] = 'c4e8a2f6b913'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEXES = (
    ('ix_result_items_task_item_id', 'result_items', 'task_item_id'),
    ('ix_tasks_automation_id', 'tasks', 'automation_id'),
    ('ix_automations_pending_task_id', 'automations', 'pending_task_id'),
)


def upgrade() -> None:
    with op.get_context().autocommit_block():
        for name, table, column in INDEXES:
            op.execute(f'CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON {table} ({column})')


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for name, _, _ in INDEXES:
            op.execute(f'DROP INDEX CONCURRENTLY IF EXISTS {name}')
