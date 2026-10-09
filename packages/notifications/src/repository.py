from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.repository import BaseRepository
from packages.notifications.src.entities import (
    NotificationDeliveryEntity,
    NotificationEventEntity,
    NotificationSettingEntity,
)
from packages.notifications.src.enums import NotificationDeliveryStatus
from packages.notifications.src.models import (
    NotificationDelivery,
    NotificationEvent,
    NotificationSetting,
)

# Окно подбора доставок автоматизации без `payload.task_id` после завершения проверочной задачи
# (свип результатов — раз в 15 секунд, на практике доставка появляется через 8–25 секунд).
LEGACY_DELIVERY_WINDOW = timedelta(minutes=5)


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

    async def update_preferences(
        self, user_id: int, preferences: dict,
    ) -> NotificationSettingEntity:
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

    async def get_by_task_id(
        self,
        task_id: UUID,
        automation_id: UUID | None = None,
        finished_at: datetime | None = None,
    ) -> list[NotificationDeliveryEntity]:
        """Доставки, порождённые задачей: `payload.task_id` проставляют и `task.*` события
        (`TaskService.complete_item`), и `automation.change_detected` (`AutomationService`).
        Поиск идёт по индексу `ix_notification_deliveries_payload_task_id` (то же выражение).

        Для проверочной задачи автоматизации (`automation_id` и `finished_at` заданы) дополнительно
        подбираются **старые** доставки без `payload.task_id` (созданы до его появления): событие
        `automation.change_detected` той же автоматизации, поставленное в течение
        `LEGACY_DELIVERY_WINDOW` после завершения задачи — доставку создаёт
        `AUTOMATION_RESULT_SWEEP` через секунды после финиша проверки. Эвристика по времени, только
        для доставок без `task_id`."""
        condition = self.model.payload['task_id'].astext == str(task_id)
        if automation_id is not None and finished_at is not None:
            condition = or_(
                condition,
                and_(
                    self.model.payload['task_id'].astext.is_(None),
                    self.model.event_code == 'automation.change_detected',
                    self.model.payload['automation_id'].astext == str(automation_id),
                    self.model.created_at >= finished_at,
                    self.model.created_at < finished_at + LEGACY_DELIVERY_WINDOW,
                ),
            )
        statement = (
            select(self.model)
            .where(condition)
            .order_by(self.model.created_at.asc(), self.model.id.asc())
        )
        database_objects = await self.session.scalars(statement)
        return self._to_entities(database_objects=database_objects)

    async def get_page_by_automation_id(
        self, automation_id: UUID, limit: int, offset: int,
    ) -> list[NotificationDeliveryEntity]:
        """Вся история уведомлений автоматизации (`payload.automation_id`), новые сверху."""
        statement = (
            select(self.model)
            .where(self.model.payload['automation_id'].astext == str(automation_id))
            .order_by(self.model.created_at.desc(), self.model.id.desc())
            .limit(limit)
            .offset(offset)
        )
        database_objects = await self.session.scalars(statement)
        return self._to_entities(database_objects=database_objects)

    async def count_by_automation_id(self, automation_id: UUID) -> int:
        statement = select(func.count(self.model.id)).where(
            self.model.payload['automation_id'].astext == str(automation_id),
        )
        return await self.session.scalar(statement)

    async def count_by_user_id(self, user_id: int) -> int:
        statement = select(func.count(self.model.id)).where(self.model.user_id == user_id)
        return await self.session.scalar(statement)

    async def claim_pending(self, limit: int) -> list[NotificationDeliveryEntity]:
        """Locks up to `limit` oldest PENDING deliveries (`FOR UPDATE SKIP LOCKED`) for the
        duration of the caller's transaction — the same protection against double-send across
        several `apps/api` replicas as `AutomationRepository.claim_due_for_dispatch`/
        `TaskRepository.claim_next`. The caller is expected to resolve every returned row to
        SENT/FAILED (`mark_sent`/`mark_failed`) before committing; a crash mid-batch leaves the
        locked rows PENDING again once the transaction rolls back, so they're simply retried by a
        later sweep — no separate "reclaim stuck deliveries" job needed, unlike
        `TASK_LEASE_RECLAIM_SWEEP` (there, a row is marked RUNNING and released *before* the
        eventual terminal write, so a crash in between needs an explicit reclaim; here the row
        never leaves PENDING until the terminal write itself)."""

        statement = (
            select(self.model)
            .where(self.model.status == NotificationDeliveryStatus.PENDING)
            .order_by(self.model.created_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        database_objects = await self.session.scalars(statement)
        return self._to_entities(database_objects=database_objects)

    async def mark_sent(self, delivery_id: int, sent_at: datetime) -> None:
        database_object = await self.session.get(entity=self.model, ident=delivery_id)
        database_object.status = NotificationDeliveryStatus.SENT
        database_object.sent_at = sent_at
        # Same explicit-flush contract as BaseRepository.update() — session.get() (unlike a
        # select()-based query) does not trigger SQLAlchemy's autoflush, so a caller that re-reads
        # this row via .get() again before the transaction commits would otherwise observe stale
        # state.
        await self.session.flush()

    async def mark_failed(self, delivery_id: int, failure_reason: str) -> None:
        database_object = await self.session.get(entity=self.model, ident=delivery_id)
        database_object.status = NotificationDeliveryStatus.FAILED
        database_object.failure_reason = failure_reason
        await self.session.flush()
