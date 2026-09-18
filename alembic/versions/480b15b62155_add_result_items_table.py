"""add result_items table

Revision ID: 480b15b62155
Revises: c3a8427ab956
Create Date: 2026-09-18 00:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '480b15b62155'
down_revision: Union[str, None] = 'c3a8427ab956'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'result_items',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('task_item_id', sa.UUID(), nullable=False),
        sa.Column(
            'marketplace',
            postgresql.ENUM('OZON', 'WILDBERRIES', name='marketplace', create_type=False),
            nullable=False,
        ),
        sa.Column(
            'parse_type',
            postgresql.ENUM(
                'PRODUCT_PAGE', 'SEARCH_QUERY', 'REVIEWS', 'CATEGORY', 'SELLER',
                name='parsetype', create_type=False,
            ),
            nullable=False,
        ),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['task_item_id'], ['task_items.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('result_items')
