from sqlalchemy.ext.asyncio import AsyncSession

from core.repository import BaseRepository
from packages.cron.src.entities import CronJobRunEntity
from packages.cron.src.models import CronJobRun


class CronJobRunRepository(BaseRepository[CronJobRun, CronJobRunEntity]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=CronJobRun, entity_object=CronJobRunEntity, session=session)
