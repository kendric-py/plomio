"""add worker_heartbeat_logs and cron_job_runs tables

Revision ID: 7a1f2c9d4e6b
Revises: 480b15b62155
Create Date: 2026-09-18 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '7a1f2c9d4e6b'
down_revision: Union[str, None] = '480b15b62155'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'worker_heartbeat_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('worker_type', sa.Enum('PARSER', 'SESSIONS', name='workertype'), nullable=False),
        sa.Column('worker_name', sa.String(), nullable=False),
        sa.Column(
            'event_type',
            sa.Enum('MISSED', 'RECOVERED', name='workerheartbeateventtype'),
            nullable=False,
        ),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'detected_at', sa.DateTime(timezone=True), server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'details', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_worker_heartbeat_logs_worker_detected_at',
        'worker_heartbeat_logs',
        ['worker_type', 'worker_name', 'detected_at'],
    )

    op.create_table(
        'cron_job_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('job', sa.Enum('WORKER_HEARTBEAT_SWEEP', name='cronjobname'), nullable=False),
        sa.Column('status', sa.Enum('SUCCESS', 'FAILURE', name='cronjobstatus'), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            'details', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False,
        ),
        sa.Column('error_reason', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('cron_job_runs')
    sa.Enum(name='cronjobstatus').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='cronjobname').drop(op.get_bind(), checkfirst=True)

    op.drop_index('ix_worker_heartbeat_logs_worker_detected_at', table_name='worker_heartbeat_logs')
    op.drop_table('worker_heartbeat_logs')
    sa.Enum(name='workerheartbeateventtype').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='workertype').drop(op.get_bind(), checkfirst=True)
