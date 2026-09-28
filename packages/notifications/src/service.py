from datetime import datetime, timezone

from core.exceptions import ObjectNotFoundError
from core.transaction_manager import AsyncTransactionManager
from packages.notifications.src.entities import (
    NotificationDeliveryEntity,
    NotificationEventEntity,
    NotificationEventPreference,
    NotificationSettingEntity,
)
from packages.notifications.src.enums import NotificationChannel, TelegramLinkOutcome
from packages.notifications.src.exceptions import (
    InvalidNotificationFieldFilterError,
    InvalidNotificationTemplateError,
    UnknownNotificationEventError,
)
from packages.notifications.src.formatting import build_message_text, get_used_variables
from packages.notifications.src.telegram_client import TelegramNotifier
from packages.notifications.src.telegram_link_store import TelegramLinkStore
from packages.notifications.src.template_catalog import get_template_variables
from packages.user.src.entities import UserEntity


def derive_gating_fields(template: str, event_code: str) -> set[str]:
    """Which fields a template implicitly subscribes to — every `{name}` in the template whose
    `template_catalog.get_template_variables(event_code)[name].field` is non-null (e.g.
    `{price_old}`/`{price_new}` -> `"PRICE"`; `{product_name}`/`{link}` have `field=None`, so they
    never gate). `notify()` uses this to gate sending on the fields the template actually *uses*,
    instead of a separately maintained `fields` filter — see AGENTS.md, "Пользовательские шаблоны
    сообщений"."""

    variable_info_map = get_template_variables(event_code=event_code)
    used_variables = get_used_variables(template=template)
    return {
        variable_info_map[variable].field
        for variable in used_variables
        if variable in variable_info_map and variable_info_map[variable].field
    }


class NotificationService:
    def __init__(
        self,
        transaction_manager: AsyncTransactionManager,
        telegram_notifier: TelegramNotifier | None = None,
        telegram_link_store: TelegramLinkStore | None = None,
    ):
        self.transaction_manager = transaction_manager
        self.telegram_notifier = telegram_notifier
        self.telegram_link_store = telegram_link_store

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
        (task.*). Если у настройки задан `template` — гейтит `derive_gating_fields(template,
        event_code)` (поля, которые шаблон реально показывает через `{name}`, из код-владеемого
        `template_catalog.py`), а не `fields`: пользователь с кастомным шаблоном подписывается на
        то, что в нём отображено, а не поддерживает два независимых списка в синхроне. Без
        `template` — как раньше, `fields`."""

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
            if preference.template:
                gating_fields = derive_gating_fields(
                    template=preference.template, event_code=event_code,
                )
                if gating_fields and not gating_fields & set(changed_fields or []):
                    return []
            elif preference.fields and not set(preference.fields) & set(changed_fields or []):
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
                if preference.template and not get_used_variables(
                    template=preference.template,
                ) <= set(get_template_variables(event_code=event_code).keys()):
                    raise InvalidNotificationTemplateError

            updated_setting = await transaction.notification_setting_repository.update_preferences(
                user_id=user_id,
                preferences={
                    event_code: {
                        'channels': [channel.value for channel in preference.channels],
                        'fields': preference.fields,
                        'template': preference.template,
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

    async def dispatch_pending(self, batch_size: int) -> dict:
        """One sweep pass over PENDING `NotificationDelivery` rows — the actual sending, run
        periodically by `NOTIFICATION_DELIVERY_SWEEP` (`packages/cron` + `apps/api/src/jobs`), the
        same pattern as `AutomationService.dispatch_due_checks`. Single attempt per delivery, no
        retry/backoff — a delivery that fails to send is terminal (FAILED), not retried by a later
        sweep (see `packages/notifications/AGENTS.md`, "Отправка"). Only TELEGRAM exists today;
        adding a channel means adding a branch here plus a notifier class like
        `TelegramNotifier`."""

        sent_count = 0
        failed_count = 0
        skipped_count = 0

        # Per-batch caches keyed by user_id — several claimed deliveries commonly belong to the
        # same user (e.g. several automation.change_detected/task.completed events queued for one
        # active user), so without this every delivery would re-fetch the same user/settings row.
        users_by_id: dict[int, UserEntity | None] = {}
        settings_by_user_id: dict[int, NotificationSettingEntity] = {}

        async with self.transaction_manager(
            use_notification_delivery_repository=True,
            use_user_repository=True,
            use_notification_setting_repository=True,
        ) as transaction:
            claimed_deliveries = await transaction.notification_delivery_repository.claim_pending(
                limit=batch_size,
            )

            for delivery in claimed_deliveries:
                if delivery.channel != NotificationChannel.TELEGRAM or self.telegram_notifier is None:
                    skipped_count += 1
                    continue

                if delivery.user_id not in users_by_id:
                    try:
                        users_by_id[delivery.user_id] = (
                            await transaction.user_repository.get_by_id(
                                entity_id=delivery.user_id,
                            )
                        )
                    except ObjectNotFoundError:
                        users_by_id[delivery.user_id] = None
                user = users_by_id[delivery.user_id]

                if user is None or user.telegram_id is None:
                    await transaction.notification_delivery_repository.mark_failed(
                        delivery_id=delivery.id,
                        failure_reason='telegram_id не привязан',
                    )
                    failed_count += 1
                    continue

                if delivery.user_id not in settings_by_user_id:
                    settings_by_user_id[delivery.user_id] = (
                        await transaction.notification_setting_repository.get_or_create(
                            user_id=delivery.user_id,
                        )
                    )
                setting = settings_by_user_id[delivery.user_id]
                preference = (setting.preferences or {}).get(delivery.event_code)
                text = build_message_text(
                    event_code=delivery.event_code,
                    payload=delivery.payload,
                    template=preference.template if preference else None,
                    template_variables=get_template_variables(event_code=delivery.event_code),
                )
                try:
                    await self.telegram_notifier.send(chat_id=user.telegram_id, text=text)
                except Exception as exc:
                    await transaction.notification_delivery_repository.mark_failed(
                        delivery_id=delivery.id,
                        failure_reason=str(exc),
                    )
                    failed_count += 1
                    continue

                await transaction.notification_delivery_repository.mark_sent(
                    delivery_id=delivery.id,
                    sent_at=datetime.now(tz=timezone.utc),
                )
                sent_count += 1

            await self.transaction_manager.commit()

        return {'sent': sent_count, 'failed': failed_count, 'skipped': skipped_count}

    async def create_telegram_link_code(self, user_id: int, ttl_seconds: int) -> str:
        """One-time code for the Telegram account-linking deep-link (`t.me/<bot>?start=<code>`,
        built by the REST layer — this service only knows the code, not the bot username). See
        `packages/notifications/AGENTS.md`, "Привязка Telegram"."""

        return await self.telegram_link_store.create_link_code(
            user_id=user_id, ttl_seconds=ttl_seconds,
        )

    async def confirm_telegram_link(self, code: str, telegram_user_id: int) -> TelegramLinkOutcome:
        """Resolves a `/start <code>` deep-link click (called from `telegram_polling.py`'s message
        handler). `code` is single-use (`TelegramLinkStore.consume_link_code` deletes it as part of
        resolving), so a retried/replayed `/start` after a successful link can't re-link a
        different account. A `telegram_id` already bound to a *different* user is left untouched —
        the caller decides what to reply, this method never silently steals a Telegram account from
        one user to give it to another."""

        user_id = await self.telegram_link_store.consume_link_code(code=code)
        if user_id is None:
            return TelegramLinkOutcome.INVALID_CODE

        async with self.transaction_manager(use_user_repository=True) as transaction:
            existing_owner = await transaction.user_repository.get_by_telegram_id(
                telegram_id=telegram_user_id,
            )
            if existing_owner is not None and existing_owner.id != user_id:
                return TelegramLinkOutcome.ALREADY_LINKED_OTHER
            if existing_owner is not None and existing_owner.id == user_id:
                return TelegramLinkOutcome.ALREADY_LINKED_SAME

            await transaction.user_repository.update(
                entity=UserEntity(id=user_id, telegram_id=telegram_user_id),
            )
            await self.transaction_manager.commit()
        return TelegramLinkOutcome.LINKED
