"""add automation article

Revision ID: e91a3c5f7b02
Revises: d4c8f215a6e9
Create Date: 2026-09-22 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e91a3c5f7b02'
down_revision: Union[str, None] = 'd4c8f215a6e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('automations', sa.Column('article', sa.String(), nullable=True))
    op.create_index(
        'ux_automations_user_marketplace_article',
        'automations',
        ['user_id', 'marketplace', 'article'],
        unique=True,
        postgresql_where=sa.text('article IS NOT NULL'),
    )


def downgrade() -> None:
    op.drop_index('ux_automations_user_marketplace_article', table_name='automations')
    op.drop_column('automations', 'article')
