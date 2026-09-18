from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from packages.worker_health.src.enums import WorkerHeartbeatEventType, WorkerType


class WorkerHeartbeatLogEntity(BaseModel):
    id: Optional[int] = Field(default=None, description='Идентификатор записи')
    worker_type: Optional[WorkerType] = Field(default=None, description='Тип воркера')
    worker_name: Optional[str] = Field(default=None, description='Имя инстанса воркера')
    event_type: Optional[WorkerHeartbeatEventType] = Field(
        default=None,
        description='Переход: пропуск heartbeat или восстановление',
    )
    last_seen_at: Optional[datetime] = Field(
        default=None,
        description='Последний известный heartbeat перед этим событием',
    )
    detected_at: Optional[datetime] = Field(
        default=None,
        description='Момент, когда переход зафиксирован проверкой',
    )
    details: Optional[dict] = Field(default=None, description='Дополнительные детали события')
