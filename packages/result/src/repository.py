from sqlalchemy.ext.asyncio import AsyncSession

from core.repository import BaseRepository
from packages.result.src.entities import ResultItemEntity
from packages.result.src.models import ResultItem


class ResultItemRepository(BaseRepository[ResultItem, ResultItemEntity]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=ResultItem, entity_object=ResultItemEntity, session=session)
