from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.database import BaseSQLModel
from packages.cron.src.enums import CronJobName, CronJobStatus


class CronJobRun(BaseSQLModel):
    __tablename__ = 'cron_job_runs'

    id: Mapped[int] = mapped_column(primary_key=True)
    job: Mapped[CronJobName] = mapped_column(SqlEnum(CronJobName), nullable=False)
    status: Mapped[CronJobStatus] = mapped_column(SqlEnum(CronJobStatus), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default='{}')
    error_reason: Mapped[str | None] = mapped_column(String, nullable=True)
