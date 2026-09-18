from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from packages.cron.src.enums import CronJobName, CronJobStatus


class CronJobRunEntity(BaseModel):
    id: Optional[int] = Field(default=None, description='Идентификатор записи')
    job: Optional[CronJobName] = Field(default=None, description='Имя job\'а')
    status: Optional[CronJobStatus] = Field(default=None, description='Результат запуска')
    started_at: Optional[datetime] = Field(default=None, description='Время начала запуска')
    finished_at: Optional[datetime] = Field(default=None, description='Время окончания запуска')
    details: Optional[dict] = Field(default=None, description='Детали запуска')
    error_reason: Optional[str] = Field(default=None, description='Текст исключения при FAILURE')
