"""rename proxy_generation_failures to session_generations and store every outcome

Revision ID: e8c4a7d12f63
Revises: d5b9f2c81e47
Create Date: 2026-10-12 18:00:00.000000

`d5b9f2c81e47` уже применена в проде, поэтому она не переписывается, а доращивается: таблица
хранит не только неудачи, но и успехи (окно «последних 50 генераций» теперь считается из БД, а не
из Redis), `proxy_id` необязателен (генерация без прокси / прокси удалён).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e8c4a7d12f63'
down_revision: Union[str, None] = 'd5b9f2c81e47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.rename_table('proxy_generation_failures', 'session_generations')
    op.execute('ALTER SEQUENCE IF EXISTS proxy_generation_failures_id_seq RENAME TO session_generations_id_seq')
    op.execute('ALTER INDEX IF EXISTS proxy_generation_failures_pkey RENAME TO session_generations_pkey')
    op.execute('ALTER INDEX ix_proxy_generation_failures_proxy_created RENAME TO ix_session_generations_proxy_created')
    op.execute('ALTER INDEX ix_proxy_generation_failures_marketplace_created RENAME TO ix_session_generations_marketplace_created')

    op.alter_column('session_generations', 'error_kind', new_column_name='outcome')
    op.execute('ALTER TYPE proxyfailurekind RENAME TO sessiongenerationoutcome')
    op.execute("ALTER TYPE sessiongenerationoutcome ADD VALUE IF NOT EXISTS 'SUCCESS'")

    op.alter_column('session_generations', 'proxy_id', existing_type=sa.Integer(), nullable=True)
    op.drop_constraint('proxy_generation_failures_proxy_id_fkey', 'session_generations', type_='foreignkey')
    op.create_foreign_key(
        'session_generations_proxy_id_fkey', 'session_generations', 'proxies',
        ['proxy_id'], ['id'], ondelete='SET NULL',
    )


def downgrade() -> None:
    # Успехи и генерации без прокси в старой схеме не помещаются — удаляются.
    op.execute("DELETE FROM session_generations WHERE outcome = 'SUCCESS' OR proxy_id IS NULL")

    op.drop_constraint('session_generations_proxy_id_fkey', 'session_generations', type_='foreignkey')
    op.create_foreign_key(
        'proxy_generation_failures_proxy_id_fkey', 'session_generations', 'proxies',
        ['proxy_id'], ['id'], ondelete='CASCADE',
    )
    op.alter_column('session_generations', 'proxy_id', existing_type=sa.Integer(), nullable=False)

    # Значение SUCCESS из enum Postgres не удаляется — оно просто остаётся неиспользуемым.
    op.execute('ALTER TYPE sessiongenerationoutcome RENAME TO proxyfailurekind')
    op.alter_column('session_generations', 'outcome', new_column_name='error_kind')

    op.execute('ALTER INDEX ix_session_generations_marketplace_created RENAME TO ix_proxy_generation_failures_marketplace_created')
    op.execute('ALTER INDEX ix_session_generations_proxy_created RENAME TO ix_proxy_generation_failures_proxy_created')
    op.execute('ALTER INDEX IF EXISTS session_generations_pkey RENAME TO proxy_generation_failures_pkey')
    op.execute('ALTER SEQUENCE IF EXISTS session_generations_id_seq RENAME TO proxy_generation_failures_id_seq')
    op.rename_table('session_generations', 'proxy_generation_failures')
