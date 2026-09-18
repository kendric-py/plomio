from datetime import datetime

from sqlalchemy import DateTime, Index, String
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from core.database import BaseSQLModel
from packages.worker_health.src.enums import WorkerHeartbeatEventType, WorkerType


class WorkerHeartbeatLog(BaseSQLModel):
    __tablename__ = 'worker_heartbeat_logs'
    __table_args__ = (
        Index(
            'ix_worker_heartbeat_logs_worker_detected_at',
            'worker_type', 'worker_name', 'detected_at',
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    worker_type: Mapped[WorkerType] = mapped_column(SqlEnum(WorkerType), nullable=False)
    worker_name: Mapped[str] = mapped_column(String, nullable=False)
    event_type: Mapped[WorkerHeartbeatEventType] = mapped_column(
        SqlEnum(WorkerHeartbeatEventType),
        nullable=False,
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default='{}')
