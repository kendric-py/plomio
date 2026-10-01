"""add BILLING_GRANT_CREDITS audit action

Revision ID: b9d3e7a25c18
Revises: a8c2e6f14d93
Create Date: 2026-10-01 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b9d3e7a25c18'
down_revision: Union[str, None] = 'a8c2e6f14d93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Колонка `audit_logs.action` — native Postgres enum, хранящий *имена* членов `AuditAction`.
    op.execute("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'BILLING_GRANT_CREDITS'")


def downgrade() -> None:
    # Postgres не умеет удалять значение из enum — оставляем, как и в других миграциях этого
    # репозитория с добавлением значения enum.
    pass
