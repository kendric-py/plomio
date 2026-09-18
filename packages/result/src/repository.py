from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.repository import BaseRepository
from packages.result.src.entities import ResultItemEntity
from packages.result.src.models import ResultItem
from packages.task.src.models import TaskItem


class ResultItemRepository(BaseRepository[ResultItem, ResultItemEntity]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=ResultItem, entity_object=ResultItemEntity, session=session)

    async def get_by_task_id(
        self,
        task_id: UUID,
        limit: int,
        offset: int,
    ) -> list[ResultItemEntity]:
        statement = (
            select(ResultItem)
            .join(TaskItem, TaskItem.id == ResultItem.task_item_id)
            .where(TaskItem.task_id == task_id)
            .order_by(ResultItem.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        database_objects = await self.session.scalars(statement)
        return self._to_entities(database_objects=database_objects)

    async def count_by_task_id(self, task_id: UUID) -> int:
        statement = (
            select(func.count(ResultItem.id))
            .join(TaskItem, TaskItem.id == ResultItem.task_item_id)
            .where(TaskItem.task_id == task_id)
        )
        return await self.session.scalar(statement)
