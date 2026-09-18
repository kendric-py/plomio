import asyncio
import logging
from datetime import datetime, timezone
from typing import Awaitable, Callable, NoReturn

from packages.cron.src.enums import CronJobName, CronJobStatus
from packages.cron.src.service import CronJobService

logger = logging.getLogger(__name__)


async def run_periodic(
    job: CronJobName,
    interval_seconds: float,
    func: Callable[[], Awaitable[dict]],
    cron_job_service: CronJobService,
) -> NoReturn:
    """Runs `func` every `interval_seconds` on the caller's event loop, logging each run via
    `cron_job_service`. A failing `func()` is caught and recorded as `FAILURE` — it does not stop
    the loop, so a single bad run doesn't silently end all future checks."""

    while True:
        await asyncio.sleep(interval_seconds)
        started_at = datetime.now(timezone.utc)
        try:
            details = await func()
            status = CronJobStatus.SUCCESS
            error_reason = None
        except Exception as exc:
            details, status, error_reason = {}, CronJobStatus.FAILURE, str(exc)
            logger.exception('[cron] job %s failed', job.value)
        await cron_job_service.record_run(
            job=job,
            status=status,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            details=details,
            error_reason=error_reason,
        )
