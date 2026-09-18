from sqlalchemy.ext.asyncio import AsyncSession

from core.repository import BaseRepository
from packages.worker_health.src.entities import WorkerHeartbeatLogEntity
from packages.worker_health.src.models import WorkerHeartbeatLog


class WorkerHeartbeatLogRepository(BaseRepository[WorkerHeartbeatLog, WorkerHeartbeatLogEntity]):
    def __init__(self, session: AsyncSession):
        super().__init__(
            model=WorkerHeartbeatLog, entity_object=WorkerHeartbeatLogEntity, session=session,
        )
