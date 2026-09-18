from datetime import datetime

from core.transaction_manager import AsyncTransactionManager
from packages.cron.src.entities import CronJobRunEntity
from packages.cron.src.enums import CronJobName, CronJobStatus


class CronJobService:
    def __init__(self, transaction_manager: AsyncTransactionManager):
        self.transaction_manager = transaction_manager

    async def record_run(
        self,
        job: CronJobName,
        status: CronJobStatus,
        started_at: datetime,
        finished_at: datetime,
        details: dict | None = None,
        error_reason: str | None = None,
    ) -> None:
        async with self.transaction_manager(use_cron_job_run_repository=True) as transaction:
            await transaction.cron_job_run_repository.create(
                entity=CronJobRunEntity(
                    job=job,
                    status=status,
                    started_at=started_at,
                    finished_at=finished_at,
                    details=details or {},
                    error_reason=error_reason,
                ),
            )
            await self.transaction_manager.commit()
