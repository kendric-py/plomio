"""add direct billing actions and DIRECT reference type

Revision ID: e5b2a8d4f631
Revises: d92a7c3e5f18
Create Date: 2026-09-29 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e5b2a8d4f631'
down_revision: Union[str, None] = 'd92a7c3e5f18'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE referencetype ADD VALUE IF NOT EXISTS 'DIRECT'")

    billing_actions_table = sa.table(
        'billing_actions',
        sa.column('action_code', sa.String()),
        sa.column('description', sa.String()),
        sa.column('base_cost', sa.Integer()),
        sa.column('unit_label', sa.String()),
    )
    op.bulk_insert(
        billing_actions_table,
        [
            {
                'action_code': 'direct.PRODUCT_PAGE',
                'description': 'Direct-запрос: карточка товара',
                'base_cost': 1,
                'unit_label': 'карточка',
            },
            {
                'action_code': 'direct.REVIEWS',
                'description': 'Direct-запрос: отзывы',
                'base_cost': 0,
                'unit_label': 'отзыв',
            },
            {
                'action_code': 'direct.SEARCH',
                'description': 'Direct-запрос: поисковая выдача',
                'base_cost': 0,
                'unit_label': 'товар',
            },
            {
                'action_code': 'direct.CATEGORY',
                'description': 'Direct-запрос: товары категории',
                'base_cost': 0,
                'unit_label': 'товар',
            },
            {
                'action_code': 'direct.SELLER',
                'description': 'Direct-запрос: товары продавца',
                'base_cost': 0,
                'unit_label': 'товар',
            },
        ],
    )


def downgrade() -> None:
    # Строки журнала ссылаются на action_code (ON DELETE SET NULL), поэтому каталог можно чистить.
    # Значение 'DIRECT' из enum `referencetype` Postgres удалить не умеет — оставляем, как и в
    # других миграциях этого репозитория с добавлением значения enum.
    op.execute("DELETE FROM billing_actions WHERE action_code LIKE 'direct.%'")
