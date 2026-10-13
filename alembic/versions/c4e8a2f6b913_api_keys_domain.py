"""api_keys domain: ключи, лимиты, учёт трат по ключу

Revision ID: c4e8a2f6b913
Revises: f1a6c3d8b972
Create Date: 2026-10-13 12:00:00.000000

Таблица `api_keys` была заглушкой (`id`, `user_id`) без значения ключа — ей нельзя было
авторизоваться, поэтому она пересоздаётся целиком. Чтобы ничего не потерять молча, миграция
останавливается, если в заглушке есть строки.

- `api_keys`: название, префикс, SHA-256-хэш (уникальный), лимит кредитов, срок действия, отзыв,
  последнее использование; FK на пользователя — `CASCADE`.
- `api_key_id` (FK `SET NULL`) у `credit_transactions` (по нему считается «потрачено по ключу»,
  индекс), `tasks` и `automations` (через какой ключ создана работа).
- значения `auditaction` для создания/изменения/отзыва ключа.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c4e8a2f6b913'
down_revision: Union[str, None] = 'f1a6c3d8b972'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

AUDIT_ACTIONS = ('API_KEY_CREATE', 'API_KEY_UPDATE', 'API_KEY_REVOKE')
REFERENCING_TABLES = ('credit_transactions', 'tasks', 'automations')


def upgrade() -> None:
    existing = op.get_bind().execute(sa.text('SELECT count(*) FROM api_keys')).scalar()
    if existing:
        raise RuntimeError(
            f'api_keys содержит {existing} строк(и) старой заглушки — проверьте их и удалите '
            'вручную перед миграцией',
        )
    op.drop_table('api_keys')
    op.create_table(
        'api_keys',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column(
            'user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False,
        ),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('prefix', sa.String(), nullable=False),
        sa.Column('key_hash', sa.String(), nullable=False),
        sa.Column('credit_limit', sa.Integer(), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.UniqueConstraint('key_hash', name='uq_api_keys_key_hash'),
    )
    op.create_index('ix_api_keys_user_id', 'api_keys', ['user_id'])

    for table in REFERENCING_TABLES:
        op.add_column(
            table,
            sa.Column(
                'api_key_id',
                sa.Integer(),
                sa.ForeignKey('api_keys.id', name=f'fk_{table}_api_key_id', ondelete='SET NULL'),
                nullable=True,
            ),
        )
    op.create_index(
        'ix_credit_transactions_api_key_id', 'credit_transactions', ['api_key_id'],
    )

    # Колонка `audit_logs.action` — native enum, хранящий *имена* членов `AuditAction`.
    for action in AUDIT_ACTIONS:
        op.execute(f"ALTER TYPE auditaction ADD VALUE IF NOT EXISTS '{action}'")


def downgrade() -> None:
    # Значения auditaction не удаляются — Postgres не умеет убирать значение из enum.
    op.drop_index('ix_credit_transactions_api_key_id', table_name='credit_transactions')
    for table in REFERENCING_TABLES:
        op.drop_constraint(f'fk_{table}_api_key_id', table, type_='foreignkey')
        op.drop_column(table, 'api_key_id')
    op.drop_index('ix_api_keys_user_id', table_name='api_keys')
    op.drop_table('api_keys')
    op.create_table(
        'api_keys',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
    )
