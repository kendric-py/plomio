from datetime import datetime

from core.transaction_manager import AsyncTransactionManager
from packages.worker_health.src.entities import WorkerHeartbeatLogEntity
from packages.worker_health.src.enums import WorkerHeartbeatEventType, WorkerType


class WorkerHealthService:
    def __init__(self, transaction_manager: AsyncTransactionManager):
        self.transaction_manager = transaction_manager

    async def record_missed(
        self,
        worker_type: WorkerType,
        worker_name: str,
        last_seen_at: datetime | None,
        details: dict | None = None,
    ) -> None:
        async with self.transaction_manager(
            use_worker_heartbeat_log_repository=True,
        ) as transaction:
            await transaction.worker_heartbeat_log_repository.create(
                entity=WorkerHeartbeatLogEntity(
                    worker_type=worker_type,
                    worker_name=worker_name,
                    event_type=WorkerHeartbeatEventType.MISSED,
                    last_seen_at=last_seen_at,
                    details=details or {},
                ),
            )
            await self.transaction_manager.commit()

    async def record_recovered(
        self,
        worker_type: WorkerType,
        worker_name: str,
        last_seen_at: datetime | None,
        details: dict | None = None,
    ) -> None:
        async with self.transaction_manager(
            use_worker_heartbeat_log_repository=True,
        ) as transaction:
            await transaction.worker_heartbeat_log_repository.create(
                entity=WorkerHeartbeatLogEntity(
                    worker_type=worker_type,
                    worker_name=worker_name,
                    event_type=WorkerHeartbeatEventType.RECOVERED,
                    last_seen_at=last_seen_at,
                    details=details or {},
                ),
            )
            await self.transaction_manager.commit()
