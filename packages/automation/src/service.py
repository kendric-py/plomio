from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from core.enums import Marketplace
from core.exceptions import DuplicatedObjectError, ObjectNotFoundError
from core.marketplace_article import extract_article
from core.transaction_manager import AsyncTransactionManager
from packages.automation.src.entities import (
    AdminAutomationFilters,
    AutomationCheckLogEntity,
    AutomationCreateData,
    AutomationEntity,
    AutomationListFilters,
    AutomationPriceChangeBucketEntity,
    AutomationPricePointEntity,
    BulkCreateResult,
)
from packages.automation.src.enums import AutomationStatus, TrackedField, TrackedFieldKind
from packages.automation.src.exceptions import DuplicateAutomationError, InvalidCheckFrequencyError
from packages.billing.src.enums import PricingDimension, ReferenceType
from packages.billing.src.exceptions import InsufficientCreditsError
from packages.billing.src.service import BillingService
from packages.notifications.src.formatting import format_changes_text
from packages.notifications.src.service import NotificationService
from packages.result.src.entities import ProductPagePayload
from packages.result.src.service import ResultService
from packages.task.src.enums import ParseType, TaskStatus
from packages.task.src.service import TaskService

# (TrackedField, kind, automation baseline attribute or None, ProductPagePayload attribute) — the
# single place that maps every tracked product-card field to how it's compared. baseline_attribute
# is None for fields without a baseline_*-column on Automation (title/rating/review_count/
# seller_name) — those participate only in the has_changes diff against the previous tick's
# snapshot, never in threshold_breached (a price-drop-specific concept, see AGENTS.md "Семантика
# базовой цены").
TRACKED_FIELDS: tuple[tuple[TrackedField, TrackedFieldKind, str | None, str], ...] = (
    (TrackedField.PRICE, TrackedFieldKind.KOPECKS, 'baseline_price_kopecks', 'price_kopecks'),
    (
        TrackedField.DISCOUNTED_PRICE, TrackedFieldKind.KOPECKS,
        'baseline_discounted_price_kopecks', 'discounted_price_kopecks',
    ),
    (
        TrackedField.ORIGINAL_PRICE, TrackedFieldKind.KOPECKS,
        'baseline_original_price_kopecks', 'original_price_kopecks',
    ),
    (TrackedField.IN_STOCK, TrackedFieldKind.BOOLEAN, 'in_stock', 'in_stock'),
    (TrackedField.TITLE, TrackedFieldKind.TEXT, None, 'title'),
    (TrackedField.RATING, TrackedFieldKind.NUMERIC, None, 'rating'),
    (TrackedField.REVIEW_COUNT, TrackedFieldKind.NUMERIC, None, 'review_count'),
    (TrackedField.SELLER_NAME, TrackedFieldKind.TEXT, None, 'seller_name'),
)

# TrackedField -> the "{name}" prefix used for its {name}_old/{name}_new notification template
# variables (packages/notifications/src/template_catalog.py::TEMPLATE_VARIABLES for
# automation.change_detected) — kept alongside TRACKED_FIELDS since it's the same field list, just
# named for template authors rather than for ProductPagePayload/Automation attribute access.
TRACKED_FIELD_VARIABLE_NAMES: dict[TrackedField, str] = {
    TrackedField.PRICE: 'price',
    TrackedField.DISCOUNTED_PRICE: 'discounted_price',
    TrackedField.ORIGINAL_PRICE: 'original_price',
    TrackedField.IN_STOCK: 'in_stock',
    TrackedField.TITLE: 'title',
    TrackedField.RATING: 'rating',
    TrackedField.REVIEW_COUNT: 'review_count',
    TrackedField.SELLER_NAME: 'seller_name',
}

_KOPECKS_FIELD_VALUES = frozenset(
    field.value for field, kind, _baseline, _payload in TRACKED_FIELDS
    if kind == TrackedFieldKind.KOPECKS
)


def filter_notifiable_changes(changes: list[dict]) -> list[dict]:
    """Изменения, о которых стоит уведомлять. Не-ценовые поля — все. Ценовые (`KOPECKS`) — только
    если порог падения относительно baseline пробит **и** цена изменилась с прошлой проверки
    (`old_value != new_value`): пока цена стабильно ниже порога, `threshold_breached` истинно на
    каждом тике (сравнение идёт с фиксированным baseline), и без второго условия пользователь
    получал бы одно и то же уведомление «1370 → 1370» каждую проверку. Первая проверка
    (`old_value is None`) считается изменением."""

    return [
        change for change in changes
        if change['field'] not in _KOPECKS_FIELD_VALUES
        or (change['threshold_breached'] and change['old_value'] != change['new_value'])
    ]


DISPATCH_PRIORITY = 5
DISPATCH_TTL = timedelta(minutes=10)
CHECK_TASK_RESULT_LIMIT = 1
RECENT_CHECKS_LIMIT = 5


# Целевое максимальное число точек графика динамики — шаг сетки подбирается под период так, чтобы
# укладываться в него (на любом периоде линия получается плотной, но не тяжёлой для фронта).
PRICE_CHART_MAX_POINTS = 30
# "Круглые" шаги сетки в секундах: 5/15/30 минут, 1/2/4/6/12 часов, 1/2/3 суток, 1/2 недели.
PRICE_CHART_STEPS_SECONDS = (
    300, 900, 1800, 3600, 7200, 14400, 21600, 43200, 86400, 172800, 259200, 604800, 1209600,
)


def price_chart_step_seconds(span: timedelta) -> int:
    """Наименьший "круглый" шаг сетки, при котором на диапазоне не больше PRICE_CHART_MAX_POINTS
    точек: сутки — 1 час, 7 дней — 6 часов, 30 дней — 1 день, 365 дней — 2 недели; при зуме в
    узкий диапазон шаг уменьшается (час — 5 минут). Один и тот же шаг у обоих графиков."""

    needed = span.total_seconds() / PRICE_CHART_MAX_POINTS
    return next(
        (step for step in PRICE_CHART_STEPS_SECONDS if step >= needed),
        PRICE_CHART_STEPS_SECONDS[-1],
    )


def align_to_step(moment: datetime, step_seconds: int) -> datetime:
    """Начало сетки: кратно шагу от эпохи — точки не "плывут" между запросами."""

    return datetime.fromtimestamp(
        moment.timestamp() // step_seconds * step_seconds, tz=timezone.utc,
    )


def fill_empty_buckets(
    points: list[AutomationPriceChangeBucketEntity],
    since: datetime,
    until: datetime,
    step_seconds: int,
) -> list[AutomationPriceChangeBucketEntity]:
    """Достраивает корзины без изменений нулями — столбчатый график непрерывный по времени."""

    delta = timedelta(seconds=step_seconds)
    counts = {point.bucket_start: point.changes_count for point in points}
    current = align_to_step(moment=since, step_seconds=step_seconds)

    filled = []
    while current <= until:
        filled.append(
            AutomationPriceChangeBucketEntity(
                bucket_start=current, changes_count=counts.get(current, 0),
            ),
        )
        current += delta
    return filled


class AutomationService:
    def __init__(
        self,
        transaction_manager: AsyncTransactionManager,
        task_service: TaskService,
        result_service: ResultService,
        billing_service: BillingService,
        notification_service: NotificationService,
        frontend_base_url: str = '',
    ):
        self.transaction_manager = transaction_manager
        self.task_service = task_service
        self.result_service = result_service
        self.billing_service = billing_service
        self.notification_service = notification_service
        self.frontend_base_url = frontend_base_url

    async def create_automation(
        self,
        user_id: int,
        marketplace: Marketplace,
        input_value: str,
        price_drop_threshold_percent: int,
        check_frequency_minutes: int,
        history_retention_days: int,
        min_check_frequency_minutes: int,
    ) -> AutomationEntity:
        if check_frequency_minutes < min_check_frequency_minutes:
            raise InvalidCheckFrequencyError

        await self.billing_service.ensure_can_spend(user_id=user_id)

        article = extract_article(marketplace=marketplace, input_value=input_value)

        async with self.transaction_manager(use_automation_repository=True) as transaction:
            duplicate = await transaction.automation_repository.find_duplicate(
                user_id=user_id, marketplace=marketplace, article=article, input_value=input_value,
            )
            if duplicate is not None:
                raise DuplicateAutomationError

            try:
                created_automation = await transaction.automation_repository.create(
                    entity=AutomationEntity(
                        user_id=user_id,
                        marketplace=marketplace,
                        input_value=input_value,
                        article=article,
                        price_drop_threshold_percent=price_drop_threshold_percent,
                        check_frequency_minutes=check_frequency_minutes,
                        history_retention_days=history_retention_days,
                        next_check_at=datetime.now(tz=timezone.utc),
                    ),
                )
            except DuplicatedObjectError as error:
                # Race window between find_duplicate and this create() — two concurrent requests
                # for the same article both passing the check above. The partial unique index
                # (user_id, marketplace, article) catches it here as a last resort.
                raise DuplicateAutomationError from error
            await self.transaction_manager.commit()

        await self.billing_service.charge(
            user_id=user_id,
            action_code='automation.create',
            reference_type=ReferenceType.AUTOMATION,
            reference_id=str(created_automation.id),
        )
        return created_automation

    async def bulk_create_automations(
        self,
        user_id: int,
        items: list[AutomationCreateData],
        min_check_frequency_minutes: int,
    ) -> list[BulkCreateResult]:
        """Batch counterpart of `create_automation`: one duplicate lookup and one multi-row INSERT
        for the whole batch instead of a query per item. Result is index-aligned with `items`;
        each element is either the created automation or the error class the single-item method
        would raise. Order of checks matches `create_automation`: frequency, then balance (a
        non-positive balance rejects every remaining item), then duplicates (against the DB and
        earlier items of the same batch). The balance is checked once for the batch and each
        created automation is then charged separately (own `reference_id`), so a batch can push
        the balance below zero — same as any single charge, see packages/billing/AGENTS.md."""

        results: list[BulkCreateResult | None] = [None] * len(items)
        candidates: list[tuple[int, AutomationEntity]] = []
        spend_block: type[InsufficientCreditsError] | None = None
        try:
            await self.billing_service.ensure_can_spend(user_id=user_id)
        except InsufficientCreditsError as error:
            spend_block = type(error)
        now = datetime.now(tz=timezone.utc)
        seen: set[tuple[Marketplace, str]] = set()

        for index, item in enumerate(items):
            if item.check_frequency_minutes < min_check_frequency_minutes:
                results[index] = BulkCreateResult(error=InvalidCheckFrequencyError)
                continue
            if spend_block is not None:
                results[index] = BulkCreateResult(error=spend_block)
                continue
            article = extract_article(marketplace=item.marketplace, input_value=item.input_value)
            key = (item.marketplace, article if article is not None else item.input_value)
            if key in seen:
                results[index] = BulkCreateResult(error=DuplicateAutomationError)
                continue
            seen.add(key)
            candidates.append((index, AutomationEntity(
                id=uuid4(),
                user_id=user_id,
                marketplace=item.marketplace,
                input_value=item.input_value,
                article=article,
                price_drop_threshold_percent=item.price_drop_threshold_percent,
                check_frequency_minutes=item.check_frequency_minutes,
                history_retention_days=item.history_retention_days,
                next_check_at=now,
            )))

        if candidates:
            entities = [entity for _, entity in candidates]
            async with self.transaction_manager(use_automation_repository=True) as transaction:
                repository = transaction.automation_repository
                duplicate_positions = await repository.find_duplicates(
                    user_id=user_id, entities=entities,
                )
                to_insert = [
                    entity for position, entity in enumerate(entities)
                    if position not in duplicate_positions
                ]
                created = {
                    automation.id: automation
                    for automation in await repository.bulk_create(entities=to_insert)
                }
                await self.transaction_manager.commit()

            for index, entity in candidates:
                automation = created.get(entity.id)
                if automation is None:
                    results[index] = BulkCreateResult(error=DuplicateAutomationError)
                    continue
                results[index] = BulkCreateResult(automation=automation)
                await self.billing_service.charge(
                    user_id=user_id,
                    action_code='automation.create',
                    reference_type=ReferenceType.AUTOMATION,
                    reference_id=str(automation.id),
                )

        return [result for result in results if result is not None]

    async def update_baseline(
        self,
        automation_id: UUID,
        user_id: int,
        price_kopecks: int | None = None,
        discounted_price_kopecks: int | None = None,
        original_price_kopecks: int | None = None,
    ) -> AutomationEntity:
        async with self.transaction_manager(use_automation_repository=True) as transaction:
            automation = await transaction.automation_repository.get_by_id(entity_id=automation_id)
            if automation.user_id != user_id:
                raise ObjectNotFoundError

            updated_automation = await transaction.automation_repository.update(
                entity=AutomationEntity(
                    id=automation_id,
                    baseline_price_kopecks=price_kopecks,
                    baseline_discounted_price_kopecks=discounted_price_kopecks,
                    baseline_original_price_kopecks=original_price_kopecks,
                ),
            )
            await self.transaction_manager.commit()
        return updated_automation

    async def pause_automation(
        self, automation_id: UUID, user_id: int | None = None,
    ) -> AutomationEntity:
        """`user_id=None` — админский вызов без проверки владельца (так же resume/delete)."""
        async with self.transaction_manager(use_automation_repository=True) as transaction:
            automation = await transaction.automation_repository.get_by_id(entity_id=automation_id)
            if user_id is not None and automation.user_id != user_id:
                raise ObjectNotFoundError

            updated_automation = await transaction.automation_repository.update(
                entity=AutomationEntity(id=automation_id, status=AutomationStatus.PAUSED),
            )
            await self.transaction_manager.commit()
        return updated_automation

    async def resume_automation(
        self, automation_id: UUID, user_id: int | None = None,
    ) -> AutomationEntity:
        async with self.transaction_manager(use_automation_repository=True) as transaction:
            automation = await transaction.automation_repository.get_by_id(entity_id=automation_id)
            if user_id is not None and automation.user_id != user_id:
                raise ObjectNotFoundError

            updated_automation = await transaction.automation_repository.update(
                entity=AutomationEntity(
                    id=automation_id,
                    status=AutomationStatus.ACTIVE,
                    next_check_at=datetime.now(tz=timezone.utc),
                ),
            )
            await self.transaction_manager.commit()
        return updated_automation

    async def delete_automation(self, automation_id: UUID, user_id: int | None = None) -> None:
        async with self.transaction_manager(use_automation_repository=True) as transaction:
            automation = await transaction.automation_repository.get_by_id(entity_id=automation_id)
            if user_id is not None and automation.user_id != user_id:
                raise ObjectNotFoundError

            await transaction.automation_repository.delete(entity_id=automation_id)
            await self.transaction_manager.commit()

    async def get_automation(
        self,
        automation_id: UUID,
        user_id: int | None = None,
    ) -> tuple[AutomationEntity, dict | None]:
        """`user_id=None` — админский доступ без проверки владельца.
        Returns the automation alongside `last_info` — the `snapshot` of its last succeeded
        check (`AutomationCheckLogRepository.get_latest_succeeded`), `None` if no check has
        succeeded yet. Separate from the automation row itself: `Automation` only carries
        derived/scalar fields (`in_stock`, baseline_*) updated by `finalize_check`, not the full
        product-card snapshot — that lives only on `AutomationCheckLog` rows."""

        async with self.transaction_manager(
            use_automation_repository=True,
            use_automation_check_log_repository=True,
        ) as transaction:
            automation = await transaction.automation_repository.get_by_id(entity_id=automation_id)
            if user_id is not None and automation.user_id != user_id:
                raise ObjectNotFoundError

            latest_succeeded = (
                await transaction.automation_check_log_repository.get_latest_succeeded(
                    automation_id=automation_id,
                )
            )
        last_info = latest_succeeded.snapshot if latest_succeeded else None
        return automation, last_info

    async def list_automations(
        self,
        user_id: int,
        limit: int,
        offset: int,
        filters: AutomationListFilters | None = None,
    ) -> tuple[list[AutomationEntity], int]:
        async with self.transaction_manager(use_automation_repository=True) as transaction:
            automations = await transaction.automation_repository.get_by_user_id(
                user_id=user_id, limit=limit, offset=offset, filters=filters,
            )
            total = await transaction.automation_repository.count_by_user_id(
                user_id=user_id, filters=filters,
            )
        return automations, total

    async def list_automations_with_recent_checks(
        self,
        user_id: int,
        limit: int,
        offset: int,
        filters: AutomationListFilters | None = None,
    ) -> tuple[list[tuple[AutomationEntity, list[AutomationCheckLogEntity]]], int]:
        """Same page of automations as `list_automations`, each paired with its last
        `RECENT_CHECKS_LIMIT` check-log ticks (newest first) — one extra batched query
        (`AutomationCheckLogRepository.get_recent_by_automation_ids`), not one query per
        automation."""

        async with self.transaction_manager(
            use_automation_repository=True,
            use_automation_check_log_repository=True,
        ) as transaction:
            automations = await transaction.automation_repository.get_by_user_id(
                user_id=user_id, limit=limit, offset=offset, filters=filters,
            )
            total = await transaction.automation_repository.count_by_user_id(
                user_id=user_id, filters=filters,
            )
            recent_checks_by_automation_id = (
                await transaction.automation_check_log_repository.get_recent_by_automation_ids(
                    automation_ids=[automation.id for automation in automations],
                    limit_per_automation=RECENT_CHECKS_LIMIT,
                )
            )
        items = [
            (automation, recent_checks_by_automation_id.get(automation.id, []))
            for automation in automations
        ]
        return items, total

    async def list_history(
        self,
        automation_id: UUID,
        user_id: int,
        limit: int,
        offset: int,
    ) -> tuple[list[AutomationCheckLogEntity], int]:
        async with self.transaction_manager(
            use_automation_repository=True,
            use_automation_check_log_repository=True,
        ) as transaction:
            automation = await transaction.automation_repository.get_by_id(entity_id=automation_id)
            if automation.user_id != user_id:
                raise ObjectNotFoundError

            items = await transaction.automation_check_log_repository.get_by_automation_id(
                automation_id=automation_id, limit=limit, offset=offset,
            )
            total = await transaction.automation_check_log_repository.count_by_automation_id(
                automation_id=automation_id,
            )
        return items, total

    async def list_automations_admin(
        self,
        filters: AdminAutomationFilters,
        limit: int,
        offset: int,
    ) -> tuple[list[AutomationEntity], int]:
        """Админский список автоматизаций всех пользователей, новые сверху."""
        async with self.transaction_manager(use_automation_repository=True) as transaction:
            items = await transaction.automation_repository.get_page_admin(
                filters=filters, limit=limit, offset=offset,
            )
            total = await transaction.automation_repository.count_admin(filters=filters)
        return items, total

    async def get_admin_summary(
        self,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> dict[str, int]:
        """Сводка автоматизаций для админки. `active`/`paused`/`overdue` — состояние на сейчас
        (просрочка = `ACTIVE`, `next_check_at` наступил, диспетчер ещё не взял), не зависит от
        периода; `checks`/`failed_checks` — тики проверок за период (`checked_at`)."""
        async with self.transaction_manager(
            use_automation_repository=True,
            use_automation_check_log_repository=True,
        ) as transaction:
            by_status = await transaction.automation_repository.count_by_status()
            overdue = await transaction.automation_repository.count_overdue()
            with_error = await transaction.automation_repository.count_with_error()
            checks, failed_checks = await transaction.automation_check_log_repository.count_ticks(
                date_from=date_from, date_to=date_to,
            )
        return {
            'active': by_status.get(AutomationStatus.ACTIVE, 0),
            'paused': by_status.get(AutomationStatus.PAUSED, 0),
            'overdue': overdue,
            'with_error': with_error,
            'checks': checks,
            'failed_checks': failed_checks,
        }

    async def get_price_dynamics(
        self,
        automation_id: UUID,
        user_id: int,
        since: datetime,
        until: datetime,
    ) -> tuple[int, list[AutomationPricePointEntity]]:
        """Регулярный ряд для графика "Динамика" на диапазоне `since..until` (зум — просто более
        узкий диапазон): шаг сетки зависит от длины диапазона (`price_chart_step_seconds`), в
        каждой точке — цена на этот момент (держится до следующего изменения), поэтому линия
        живая и без пропусков. `changed` — цена в точке отличается от предыдущей."""

        step_seconds = price_chart_step_seconds(span=until - since)
        async with self.transaction_manager(
            use_automation_repository=True,
            use_automation_check_log_repository=True,
        ) as transaction:
            automation = await transaction.automation_repository.get_by_id(entity_id=automation_id)
            if automation.user_id != user_id:
                raise ObjectNotFoundError
            points = await transaction.automation_check_log_repository.get_price_dynamics(
                automation_id=automation_id,
                start=align_to_step(moment=since, step_seconds=step_seconds),
                until=until,
                step_seconds=step_seconds,
            )

        previous = None
        for point in points:
            current = (
                point.price_kopecks, point.discounted_price_kopecks, point.original_price_kopecks,
            )
            point.changed = previous is not None and current != previous
            previous = current
        return step_seconds, points

    async def get_price_change_frequency(
        self,
        automation_id: UUID,
        user_id: int,
        since: datetime,
        until: datetime,
    ) -> tuple[int, list[AutomationPriceChangeBucketEntity]]:
        """Точки графика "Частота изменения цен" на диапазоне `since..until`: число изменений
        цены на корзину времени. Шаг тот же, что у динамики (`price_chart_step_seconds`) —
        оси двух графиков совпадают, при зуме меняются вместе."""

        step_seconds = price_chart_step_seconds(span=until - since)
        async with self.transaction_manager(
            use_automation_repository=True,
            use_automation_check_log_repository=True,
        ) as transaction:
            automation = await transaction.automation_repository.get_by_id(entity_id=automation_id)
            if automation.user_id != user_id:
                raise ObjectNotFoundError
            points = await transaction.automation_check_log_repository.get_price_change_frequency(
                automation_id=automation_id, since=since, until=until, step_seconds=step_seconds,
            )
        filled = fill_empty_buckets(
            points=points, since=since, until=until, step_seconds=step_seconds,
        )
        return step_seconds, filled

    async def dispatch_due_checks(
        self,
        batch_size: int,
        out_of_stock_check_frequency_minutes: int,
    ) -> dict:
        # Claiming (this transaction) and creating the check Task (task_service's own, separate
        # transaction/session) must not overlap: tasks.automation_id's FK has to lock the very
        # automation row that claim_due_for_dispatch's FOR UPDATE SKIP LOCKED just locked, so
        # holding that lock open across the cross-session INSERT deadlocks the two connections
        # against each other. Committing here first, before any task_service call, avoids it.
        async with self.transaction_manager(use_automation_repository=True) as transaction:
            claimed_automations = await transaction.automation_repository.claim_due_for_dispatch(
                now=datetime.now(tz=timezone.utc),
                limit=batch_size,
                out_of_stock_check_frequency_minutes=out_of_stock_check_frequency_minutes,
            )
            await self.transaction_manager.commit()

        # One batched balance lookup for every distinct user in this dispatch batch instead of one
        # has_positive_balance() round trip per automation — several claimed automations commonly
        # belong to the same user (multiple monitored products).
        blocked_reasons = await self.billing_service.get_blocked_user_ids(
            user_ids=list({automation.user_id for automation in claimed_automations}),
        )

        dispatched_count = 0
        for automation in claimed_automations:
            # next_check_at was already advanced by claim_due_for_dispatch above regardless of
            # this guard — an automation skipped here for insufficient credits simply sits out
            # this cycle and is reconsidered at its next (already-advanced) next_check_at, not
            # retried immediately; see packages/billing/AGENTS.md.
            if automation.user_id in blocked_reasons:
                async with self.transaction_manager(use_automation_repository=True) as transaction:
                    await transaction.automation_repository.finalize_check(
                        automation_id=automation.id,
                        last_checked_at=datetime.now(tz=timezone.utc),
                        last_check_error=blocked_reasons[automation.user_id],
                        baseline_updates={},
                    )
                    await self.transaction_manager.commit()
                continue

            task = await self.task_service.create_task(
                parse_type=ParseType.PRODUCT_PAGE,
                marketplace=automation.marketplace,
                inputs=[automation.input_value],
                priority=DISPATCH_PRIORITY,
                ttl=DISPATCH_TTL,
                user_id=automation.user_id,
                result_limit=CHECK_TASK_RESULT_LIMIT,
                automation_id=automation.id,
                pricing_dimension_code=PricingDimension.AUTOMATION_CHECK_FREQUENCY.value,
                pricing_dimension_value=automation.check_frequency_minutes,
            )
            async with self.transaction_manager(use_automation_repository=True) as transaction:
                await transaction.automation_repository.set_pending_task(
                    automation_id=automation.id, task_id=task.id,
                )
                await self.transaction_manager.commit()
            dispatched_count += 1
        return {'dispatched': dispatched_count}

    async def process_pending_results(self, batch_size: int) -> dict:
        # notify() calls are collected here and only fired after this transaction commits (below,
        # outside the `async with` block) — see packages/notifications/AGENTS.md, "Кто сейчас
        # вызывает notify" / packages/automation/AGENTS.md, "Композиция сервисов и транзакции".
        # Calling notify() from inside _finalize_check while this transaction was still open let a
        # later automation's failure in the same batch roll back an earlier automation's
        # AutomationCheckLog write and pending_task_id clearing, while that earlier automation's
        # NotificationDelivery (written and committed by NotificationService's own, separate
        # transaction) survived — an orphaned notification for a tick the DB no longer has any
        # record of, and a duplicate one on the next sweep once pending_task_id never cleared.
        pending_notifications: list[dict] = []

        async with self.transaction_manager(
            use_automation_repository=True,
            use_automation_check_log_repository=True,
        ) as transaction:
            awaiting_automations = await transaction.automation_repository.get_awaiting_result(
                limit=batch_size,
            )

            # One batched fetch for every pending task in this sweep batch instead of one
            # get_task_by_id() round trip per automation.
            tasks_by_id = {
                task.id: task
                for task in await self.task_service.get_tasks_by_ids(
                    task_ids=[automation.pending_task_id for automation in awaiting_automations],
                )
            }

            processed_count = 0
            changes_detected_count = 0
            for automation in awaiting_automations:
                task = tasks_by_id.get(automation.pending_task_id)
                if task is None or task.status not in (
                    TaskStatus.SUCCEEDED,
                    TaskStatus.FAILED,
                    TaskStatus.EXPIRED,
                    TaskStatus.CANCELLED,
                ):
                    continue

                changes_detected, notify_call = await self._finalize_check(
                    transaction=transaction, automation=automation, task_status=task.status,
                )
                changes_detected_count += changes_detected
                if notify_call is not None:
                    pending_notifications.append(notify_call)
                processed_count += 1
            await self.transaction_manager.commit()

        for notify_call in pending_notifications:
            await self.notification_service.notify(**notify_call)

        return {'processed': processed_count, 'changes_detected': changes_detected_count}

    async def _finalize_check(
        self,
        transaction: AsyncTransactionManager,
        automation: AutomationEntity,
        task_status: TaskStatus,
    ) -> tuple[int, dict | None]:
        """Записывает ровно одну строку AutomationCheckLog на каждый финализируемый тик,
        независимо от исхода (успех/провал/успех без изменений), в отличие от прежнего поведения
        (строка только при успехе с реальным изменением). has_changes считается относительно
        снимка ПРЕДЫДУЩЕГО успешного тика, threshold_breached — относительно baseline на
        Automation, как раньше (см. AGENTS.md, "Семантика базовой цены"). Returns
        `(changes_detected, notify_call)` — `notify_call` is the `**kwargs` for
        `NotificationService.notify(...)` if `has_changes or threshold_breached`, else `None`; the
        caller (`process_pending_results`) is responsible for actually calling `notify()`, and only
        after its own transaction commits — this method must stay side-effect-free with respect to
        anything outside `transaction`."""

        succeeded = task_status == TaskStatus.SUCCEEDED
        error_message: str | None = None
        last_check_error: str | None = None
        snapshot: dict | None = None
        previous_snapshot: dict | None = None
        product_name: str | None = None
        product_link: str | None = None
        changes: list[dict] = []
        has_changes = False
        threshold_breached = False
        baseline_updates: dict[str, int | bool] = {}
        current_values: dict[str, int | str | None] = {}

        if succeeded:
            results, _ = await self.result_service.get_results_for_task(
                task_id=automation.pending_task_id, limit=CHECK_TASK_RESULT_LIMIT, offset=0,
            )
            if results:
                payload = ProductPagePayload.model_validate(results[0].payload)
                snapshot = self._build_snapshot(payload=payload)
                product_name = payload.title
                product_link = payload.product_url
                current_values = {
                    'name': payload.title,
                    'price_kopecks': payload.price_kopecks,
                    'discounted_price_kopecks': payload.discounted_price_kopecks,
                    'original_price_kopecks': payload.original_price_kopecks,
                }

                previous_log = (
                    await transaction.automation_check_log_repository.get_latest_succeeded(
                        automation_id=automation.id,
                    )
                )
                previous_snapshot = previous_log.snapshot if previous_log else None
                changes, threshold_breached, baseline_updates = (
                    self._diff_against_previous_and_baseline(
                        automation=automation,
                        payload=payload,
                        previous_snapshot=previous_snapshot,
                    )
                )
                has_changes = bool(changes)
            else:
                succeeded = False
                error_message = 'check_task_no_result'
                last_check_error = error_message
        else:
            error_message = f'check_task_{task_status.value.lower()}'
            last_check_error = error_message

        await transaction.automation_check_log_repository.create(
            entity=AutomationCheckLogEntity(
                automation_id=automation.id,
                succeeded=succeeded,
                error_message=error_message,
                snapshot=snapshot,
                changes=changes,
                has_changes=has_changes,
                threshold_breached=threshold_breached,
            ),
        )

        await transaction.automation_repository.finalize_check(
            automation_id=automation.id,
            last_checked_at=datetime.now(tz=timezone.utc),
            last_check_error=last_check_error,
            baseline_updates=baseline_updates,
            current_values=current_values,
        )

        notify_call: dict | None = None
        # Ценовые изменения уведомляют только при пробитии порога падения относительно baseline и
        # только если цена изменилась с прошлой проверки (см. `filter_notifiable_changes`) — всё
        # остальное в лог пишем как есть, но уведомлять не о чем.
        changes = filter_notifiable_changes(changes=changes)
        threshold_breached = any(change['threshold_breached'] for change in changes)
        if changes:
            notify_payload = {
                'automation_id': str(automation.id),
                # Проверочная задача этого тика — по ней админка находит доставки задачи.
                'task_id': str(automation.pending_task_id),
                'product_name': product_name,
                'link': product_link,
                'automation_link': (
                    f'{self.frontend_base_url}/automations/{automation.id}'
                    if self.frontend_base_url else None
                ),
                'changes': changes,
                'changes_text': format_changes_text(changes=changes),
                'threshold_breached': threshold_breached,
            }
            for field, _kind, _baseline_attribute, _payload_attribute in TRACKED_FIELDS:
                variable_name = TRACKED_FIELD_VARIABLE_NAMES[field]
                notify_payload[f'{variable_name}_old'] = (
                    previous_snapshot.get(field.value) if previous_snapshot else None
                )
                notify_payload[f'{variable_name}_new'] = (
                    snapshot.get(field.value) if snapshot else None
                )

            notify_call = {
                'user_id': automation.user_id,
                'event_code': 'automation.change_detected',
                'payload': notify_payload,
                'changed_fields': [change['field'] for change in changes],
            }

        return (1 if has_changes else 0), notify_call

    def _build_snapshot(self, payload: ProductPagePayload) -> dict:
        """Снимок всех TrackedField из текущего payload — сохраняется на этой строке лога и
        используется как база сравнения для СЛЕДУЮЩЕГО тика (см. get_latest_succeeded)."""

        return {
            field.value: getattr(payload, payload_attribute)
            for field, _kind, _baseline_attribute, payload_attribute in TRACKED_FIELDS
        }

    def _diff_against_previous_and_baseline(
        self,
        automation: AutomationEntity,
        payload: ProductPagePayload,
        previous_snapshot: dict | None,
    ) -> tuple[list[dict], bool, dict[str, int | bool]]:
        """Единый проход по всем TrackedField. has_changes — новое значение против
        previous_snapshot (снимок предыдущего успешного тика; None на самом первом успешном тике —
        изменений тогда нет). threshold_breached — новое значение против Automation.baseline_*/
        in_stock, только для KOPECKS-полей и восстановления наличия (IN_STOCK False -> True) — та
        же математика, что раньше в _diff_prices/_diff_stock. baseline_updates сохраняет прежний
        контракт: сеет baseline на первой проверке (baseline_value is None), обновляет in_stock на
        любое реальное изменение."""

        changes: list[dict] = []
        baseline_updates: dict[str, int | bool] = {}

        for field, kind, baseline_attribute, payload_attribute in TRACKED_FIELDS:
            new_value = getattr(payload, payload_attribute)
            if new_value is None:
                continue

            previous_value = previous_snapshot.get(field.value) if previous_snapshot else None
            field_changed = previous_snapshot is not None and new_value != previous_value

            field_threshold_breached = False
            if baseline_attribute is not None:
                baseline_value = getattr(automation, baseline_attribute)
                if baseline_value is None:
                    baseline_updates[baseline_attribute] = new_value
                elif new_value != baseline_value:
                    if kind == TrackedFieldKind.KOPECKS:
                        threshold_price = (
                            baseline_value * (100 - automation.price_drop_threshold_percent) / 100
                        )
                        field_threshold_breached = new_value <= threshold_price
                    elif kind == TrackedFieldKind.BOOLEAN:
                        field_threshold_breached = new_value is True
                        baseline_updates[baseline_attribute] = new_value

            if field_changed or field_threshold_breached:
                changes.append(
                    {
                        'field': field.value,
                        'old_value': previous_value,
                        'new_value': new_value,
                        'threshold_breached': field_threshold_breached,
                    },
                )

        threshold_breached = any(change['threshold_breached'] for change in changes)
        return changes, threshold_breached, baseline_updates

    async def sweep_history_retention(self) -> int:
        async with self.transaction_manager(
            use_automation_check_log_repository=True,
        ) as transaction:
            deleted_count = await transaction.automation_check_log_repository.delete_expired()
            await self.transaction_manager.commit()
        return deleted_count
