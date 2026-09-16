from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.repository import BaseRepository
from packages.user.src.entities import UserEntity
from packages.user.src.models import User


class UserRepository(BaseRepository[User, UserEntity]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=User, entity_object=UserEntity, session=session)

    async def get_by_email(self, email: str) -> Optional[UserEntity]:
        statement = select(self.model).where(self.model.email == email)
        database_object = await self.session.scalar(statement)
        if database_object is None:
            return None
        return self._to_entity(database_object=database_object)

    async def get_by_telegram_id(self, telegram_id: int) -> Optional[UserEntity]:
        statement = select(self.model).where(self.model.telegram_id == telegram_id)
        database_object = await self.session.scalar(statement)
        if database_object is None:
            return None
        return self._to_entity(database_object=database_object)
