from datetime import datetime

from pydantic import BaseModel, Field

from packages.worker_health.src.enums import WorkerType


class HeartbeatRequest(BaseModel):
    worker_name: str = Field(description='Имя инстанса воркера (LIVENESS_WORKER_NAME)')
    status: str = Field(description='Текущий статус воркера (например READY/WORKING)')


class HeartbeatResponse(BaseModel):
    accepted: bool = Field(description='Heartbeat принят')


class WorkerStatusItem(BaseModel):
    worker_type: WorkerType = Field(description='Тип воркера')
    worker_name: str = Field(description='Имя инстанса воркера')
    status: str | None = Field(
        default=None,
        description='Последний статус, присланный воркером в heartbeat (например READY/WORKING); '
        '`null`, если heartbeat был получен до появления этого поля',
    )
    last_seen_at: datetime = Field(description='Время последнего полученного heartbeat')
    gap_seconds: float = Field(description='Сколько секунд прошло с последнего heartbeat')
    is_missed: bool = Field(
        description='Воркер сейчас считается пропустившим heartbeat (в этом состоянии '
        'уже записана MISSED-запись в worker_heartbeat_logs)',
    )


class WorkerStatusResponse(BaseModel):
    workers: list[WorkerStatusItem] = Field(description='Известные воркеры и их текущий статус')
