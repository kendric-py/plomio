from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import ObjectNotFoundError
from core.repository import BaseRepository
from packages.api_keys.src.entities import ApiKeyEntity
from packages.api_keys.src.models import ApiKey


class ApiKeyRepository(BaseRepository[ApiKey, ApiKeyEntity]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=ApiKey, entity_object=ApiKeyEntity, session=session)

    async def get_by_hash(self, key_hash: str) -> ApiKeyEntity | None:
        database_object = await self.session.scalar(
            select(self.model).where(self.model.key_hash == key_hash),
        )
        return self._to_entity(database_object=database_object) if database_object else None

    async def get_by_user_id(self, user_id: int) -> list[ApiKeyEntity]:
        """Все ключи пользователя, новые сверху. Без пагинации: ключей у пользователя единицы
        (действующих — не больше квоты сервиса)."""
        statement = (
            select(self.model)
            .where(self.model.user_id == user_id)
            .order_by(self.model.created_at.desc(), self.model.id.desc())
        )
        return self._to_entities(database_objects=await self.session.scalars(statement))

    async def get_by_ids(self, api_key_ids: list[int]) -> list[ApiKeyEntity]:
        if not api_key_ids:
            return []
        statement = select(self.model).where(self.model.id.in_(api_key_ids))
        return self._to_entities(database_objects=await self.session.scalars(statement))

    async def count_not_revoked(self, user_id: int) -> int:
        statement = select(func.count()).where(
            self.model.user_id == user_id, self.model.revoked_at.is_(None),
        )
        return await self.session.scalar(statement)

    async def apply_changes(self, api_key_id: int, values: dict) -> ApiKeyEntity:
        """Сырой `UPDATE`: в отличие от `BaseRepository.update` умеет записывать `NULL` (снять
        лимит или срок действия)."""
        statement = (
            update(self.model)
            .where(self.model.id == api_key_id)
            .values(**values, updated_at=func.now())
            .returning(self.model)
        )
        database_object = await self.session.scalar(statement)
        if database_object is None:
            raise ObjectNotFoundError
        return self._to_entity(database_object=database_object)

    async def touch_last_used(self, api_key_id: int, used_at: datetime) -> None:
        """Без `updated_at`: это не изменение ключа пользователем."""
        await self.session.execute(
            update(self.model)
            .where(self.model.id == api_key_id)
            .values(last_used_at=used_at)
            .execution_options(synchronize_session=False),
        )
