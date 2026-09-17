from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from core.database import BaseSQLModel
from packages.audit_log.src.enums import AuditAction, AuditActionType, AuditStatus


class AuditLog(BaseSQLModel):
    __tablename__ = 'audit_logs'

    id: Mapped[int] = mapped_column(primary_key=True)
    action: Mapped[AuditAction] = mapped_column(SqlEnum(AuditAction), nullable=False)
    action_type: Mapped[AuditActionType] = mapped_column(SqlEnum(AuditActionType), nullable=False)
    status: Mapped[AuditStatus] = mapped_column(SqlEnum(AuditStatus), nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default='{}')
    error_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    target_type: Mapped[str | None] = mapped_column(String, nullable=True)
    target_id: Mapped[int | None] = mapped_column(nullable=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
    )
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
