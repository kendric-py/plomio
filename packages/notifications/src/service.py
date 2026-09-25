from core.transaction_manager import AsyncTransactionManager
from packages.notifications.src.entities import (
    NotificationDeliveryEntity,
    NotificationEventEntity,
    NotificationEventPreference,
    NotificationSettingEntity,
)
from packages.notifications.src.exceptions import (
    InvalidNotificationFieldFilterError,
    UnknownNotificationEventError,
)


class NotificationService:
    def __init__(self, transaction_manager: AsyncTransactionManager):
        self.transaction_manager = transaction_manager

    async def notify(
        self,
        user_id: int,
        event_code: str,
        payload: dict,
        changed_fields: list[str] | None = None,
    ) -> list[NotificationDeliveryEntity]:
        """Единственная точка интеграции — вызывается любым доменом (automation, task, в будущем —
        другими) при наступлении события. No-op (возвращает [], ничего не пишет), если event_code
        не в каталоге/неактивен, или пользователь не включил ни одного канала для этого события —
        вызывающий домен никогда не должен падать из-за отсутствующей/выключенной настройки, тот
        же контракт, что у BillingService.charge. `changed_fields` — какие поля затронуло это
        конкретное срабатывание события (например, TrackedField-значения из
        AutomationCheckLog.changes); домен передаёт `None`, если у события нет понятия "поле"
        (task.*). Канал срабатывает, если у настройки нет фильтра `fields`, либо он пересекается с
        `changed_fields`."""

        async with self.transaction_manager(
            use_notification_event_repository=True,
            use_notification_setting_repository=True,
            use_notification_delivery_repository=True,
        ) as transaction:
            event = await transaction.notification_event_repository.get_by_code(
                event_code=event_code,
            )
            if event is None or not event.is_active:
                return []

            setting = await transaction.notification_setting_repository.get_or_create(
                user_id=user_id,
            )
            preference = (setting.preferences or {}).get(event_code)
            if preference is None or not preference.channels:
                return []
            if preference.fields and not set(preference.fields) & set(changed_fields or []):
                return []

            created_deliveries: list[NotificationDeliveryEntity] = []
            for channel in preference.channels:
                created_delivery = await transaction.notification_delivery_repository.create(
                    entity=NotificationDeliveryEntity(
                        user_id=user_id,
                        event_code=event_code,
                        channel=channel,
                        payload=payload,
                    ),
                )
                created_deliveries.append(created_delivery)
            await self.transaction_manager.commit()
        return created_deliveries

    async def get_preferences(self, user_id: int) -> NotificationSettingEntity:
        async with self.transaction_manager(
            use_notification_setting_repository=True,
        ) as transaction:
            setting = await transaction.notification_setting_repository.get_or_create(
                user_id=user_id,
            )
            await self.transaction_manager.commit()
        return setting

    async def update_preferences(
        self, user_id: int, preferences: dict[str, NotificationEventPreference],
    ) -> NotificationSettingEntity:
        async with self.transaction_manager(
            use_notification_event_repository=True,
            use_notification_setting_repository=True,
        ) as transaction:
            for event_code, preference in preferences.items():
                event = await transaction.notification_event_repository.get_by_code(
                    event_code=event_code,
                )
                if event is None or not event.is_active:
                    raise UnknownNotificationEventError
                if preference.fields and not set(preference.fields) <= set(
                    event.available_fields or [],
                ):
                    raise InvalidNotificationFieldFilterError

            updated_setting = await transaction.notification_setting_repository.update_preferences(
                user_id=user_id,
                preferences={
                    event_code: {
                        'channels': [channel.value for channel in preference.channels],
                        'fields': preference.fields,
                    }
                    for event_code, preference in preferences.items()
                },
            )
            await self.transaction_manager.commit()
        return updated_setting

    async def list_deliveries(
        self, user_id: int, limit: int, offset: int,
    ) -> tuple[list[NotificationDeliveryEntity], int]:
        async with self.transaction_manager(
            use_notification_delivery_repository=True,
        ) as transaction:
            items = await transaction.notification_delivery_repository.get_by_user_id(
                user_id=user_id, limit=limit, offset=offset,
            )
            total = await transaction.notification_delivery_repository.count_by_user_id(
                user_id=user_id,
            )
        return items, total

    async def list_events(self) -> list[NotificationEventEntity]:
        async with self.transaction_manager(use_notification_event_repository=True) as transaction:
            return await transaction.notification_event_repository.list_active()
