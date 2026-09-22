import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from core.database import BaseSQLModel
from core.enums import Marketplace
from packages.task.src.enums import ParseType, TaskItemStatus, TaskStatus


class Task(BaseSQLModel):
    __tablename__ = 'tasks'
    __table_args__ = (
        CheckConstraint('priority BETWEEN 1 AND 10', name='ck_tasks_priority_range'),
    )
    # eager_defaults: updated_at is server-computed (onupdate=func.now()) — without this,
    # reading it back right after an async UPDATE fails with MissingGreenlet, since SQLAlchemy
    # would otherwise lazily re-fetch it outside the async context.
    __mapper_args__ = {'eager_defaults': True}

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    parse_type: Mapped[ParseType] = mapped_column(SqlEnum(ParseType), nullable=False)
    marketplace: Mapped[Marketplace] = mapped_column(SqlEnum(Marketplace), nullable=False)
    status: Mapped[TaskStatus] = mapped_column(
        SqlEnum(TaskStatus),
        nullable=False,
        server_default=TaskStatus.QUEUED.value,
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    queue_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    result_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    claimed_by: Mapped[str | None] = mapped_column(String, nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    error_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    # Set once at creation by packages.automation (a check task, not a user-initiated one) and
    # never cleared afterwards — unlike Automation.pending_task_id, which is cleared once the
    # check completes. This is the only way to tell a check task apart from a regular one once
    # that link is gone, so REST listing (see packages.task.src.repository) can hide it by default.
    automation_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey('automations.id', ondelete='SET NULL'),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class TaskItem(BaseSQLModel):
    __tablename__ = 'task_items'
    __table_args__ = (
        UniqueConstraint(
            'task_id',
            'position',
            name='uq_task_items_task_position',
        ),
    )
    __mapper_args__ = {'eager_defaults': True}

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey('tasks.id', ondelete='CASCADE'),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    input_value: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[TaskItemStatus] = mapped_column(
        SqlEnum(TaskItemStatus),
        nullable=False,
        server_default=TaskItemStatus.PENDING.value,
    )
    cursor: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    result_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default='0')
    error_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
