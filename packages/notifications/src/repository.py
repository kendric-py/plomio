from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.repository import BaseRepository
from packages.notifications.src.entities import (
    NotificationDeliveryEntity,
    NotificationEventEntity,
    NotificationSettingEntity,
)
from packages.notifications.src.models import (
    NotificationDelivery,
    NotificationEvent,
    NotificationSetting,
)


class NotificationEventRepository(BaseRepository[NotificationEvent, NotificationEventEntity]):
    def __init__(self, session: AsyncSession):
        super().__init__(
            model=NotificationEvent, entity_object=NotificationEventEntity, session=session,
        )

    async def get_by_code(self, event_code: str) -> NotificationEventEntity | None:
        statement = select(self.model).where(self.model.event_code == event_code)
        database_object = await self.session.scalar(statement)
        return self._to_entity(database_object=database_object) if database_object else None

    async def list_active(self) -> list[NotificationEventEntity]:
        statement = select(self.model).where(self.model.is_active.is_(True))
        database_objects = await self.session.scalars(statement)
        return self._to_entities(database_objects=database_objects)


class NotificationSettingRepository(BaseRepository[NotificationSetting, NotificationSettingEntity]):
    def __init__(self, session: AsyncSession):
        super().__init__(
            model=NotificationSetting, entity_object=NotificationSettingEntity, session=session,
        )

    async def get_or_create(self, user_id: int) -> NotificationSettingEntity:
        """Настройки должны существовать при первом обращении — по образцу
        CreditWalletRepository.lock_or_create, но без row lock: preferences читаются и полностью
        заменяются через update_preferences под ответственностью вызывающего сервиса, конкурентная
        запись здесь не более рискованна, чем у обычного BaseRepository.update."""

        database_object = await self.session.get(entity=self.model, ident=user_id)
        if database_object is None:
            database_object = self.model(user_id=user_id, preferences={})
            self.session.add(database_object)
            await self.session.flush()
        return self._to_entity(database_object=database_object)

    async def update_preferences(self, user_id: int, preferences: dict) -> NotificationSettingEntity:
        database_object = await self.session.get(entity=self.model, ident=user_id)
        if database_object is None:
            database_object = self.model(user_id=user_id, preferences=preferences)
            self.session.add(database_object)
        else:
            database_object.preferences = preferences
        await self.session.flush()
        return self._to_entity(database_object=database_object)


class NotificationDeliveryRepository(
    BaseRepository[NotificationDelivery, NotificationDeliveryEntity],
):
    def __init__(self, session: AsyncSession):
        super().__init__(
            model=NotificationDelivery, entity_object=NotificationDeliveryEntity, session=session,
        )

    async def get_by_user_id(
        self, user_id: int, limit: int, offset: int,
    ) -> list[NotificationDeliveryEntity]:
        statement = (
            select(self.model)
            .where(self.model.user_id == user_id)
            .order_by(self.model.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        database_objects = await self.session.scalars(statement)
        return self._to_entities(database_objects=database_objects)

    async def count_by_user_id(self, user_id: int) -> int:
        statement = select(func.count(self.model.id)).where(self.model.user_id == user_id)
        return await self.session.scalar(statement)
