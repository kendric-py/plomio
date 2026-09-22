from datetime import datetime, timedelta, timezone
from uuid import UUID

from core.enums import Marketplace
from core.exceptions import DuplicatedObjectError, ObjectNotFoundError
from core.marketplace_article import extract_article
from core.transaction_manager import AsyncTransactionManager
from packages.automation.src.entities import AutomationEntity, AutomationHistoryEntity
from packages.automation.src.enums import AutomationStatus, PriceField
from packages.automation.src.exceptions import DuplicateAutomationError, InvalidCheckFrequencyError
from packages.result.src.entities import ProductPagePayload
from packages.result.src.service import ResultService
from packages.task.src.enums import ParseType, TaskStatus
from packages.task.src.service import TaskService

# (PriceField, automation baseline attribute, payload attribute) — the single place that maps a
# tracked price to where its baseline lives on Automation and where its current value comes from
# in ProductPagePayload, so dispatch/compare logic doesn't repeat the three fields by hand.
TRACKED_PRICE_FIELDS: tuple[tuple[PriceField, str, str], ...] = (
    (PriceField.PRICE, 'baseline_price_kopecks', 'price_kopecks'),
    (PriceField.DISCOUNTED_PRICE, 'baseline_discounted_price_kopecks', 'discounted_price_kopecks'),
    (PriceField.ORIGINAL_PRICE, 'baseline_original_price_kopecks', 'original_price_kopecks'),
)

DISPATCH_PRIORITY = 5
DISPATCH_TTL = timedelta(minutes=10)
CHECK_TASK_RESULT_LIMIT = 1


class AutomationService:
    def __init__(
        self,
        transaction_manager: AsyncTransactionManager,
        task_service: TaskService,
        result_service: ResultService,
    ):
        self.transaction_manager = transaction_manager
        self.task_service = task_service
        self.result_service = result_service

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
        return created_automation

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

    async def pause_automation(self, automation_id: UUID, user_id: int) -> AutomationEntity:
        async with self.transaction_manager(use_automation_repository=True) as transaction:
            automation = await transaction.automation_repository.get_by_id(entity_id=automation_id)
            if automation.user_id != user_id:
                raise ObjectNotFoundError

            updated_automation = await transaction.automation_repository.update(
                entity=AutomationEntity(id=automation_id, status=AutomationStatus.PAUSED),
            )
            await self.transaction_manager.commit()
        return updated_automation

    async def resume_automation(self, automation_id: UUID, user_id: int) -> AutomationEntity:
        async with self.transaction_manager(use_automation_repository=True) as transaction:
            automation = await transaction.automation_repository.get_by_id(entity_id=automation_id)
            if automation.user_id != user_id:
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

    async def delete_automation(self, automation_id: UUID, user_id: int) -> None:
        async with self.transaction_manager(use_automation_repository=True) as transaction:
            automation = await transaction.automation_repository.get_by_id(entity_id=automation_id)
            if automation.user_id != user_id:
                raise ObjectNotFoundError

            await transaction.automation_repository.delete(entity_id=automation_id)
            await self.transaction_manager.commit()

    async def get_automation(self, automation_id: UUID, user_id: int) -> AutomationEntity:
        async with self.transaction_manager(use_automation_repository=True) as transaction:
            automation = await transaction.automation_repository.get_by_id(entity_id=automation_id)
            if automation.user_id != user_id:
                raise ObjectNotFoundError
            return automation

    async def list_automations(
        self,
        user_id: int,
        limit: int,
        offset: int,
    ) -> tuple[list[AutomationEntity], int]:
        async with self.transaction_manager(use_automation_repository=True) as transaction:
            automations = await transaction.automation_repository.get_by_user_id(
                user_id=user_id, limit=limit, offset=offset,
            )
            total = await transaction.automation_repository.count_by_user_id(user_id=user_id)
        return automations, total

    async def list_history(
        self,
        automation_id: UUID,
        user_id: int,
        limit: int,
        offset: int,
    ) -> tuple[list[AutomationHistoryEntity], int]:
        async with self.transaction_manager(
            use_automation_repository=True,
            use_automation_history_repository=True,
        ) as transaction:
            automation = await transaction.automation_repository.get_by_id(entity_id=automation_id)
            if automation.user_id != user_id:
                raise ObjectNotFoundError

            items = await transaction.automation_history_repository.get_by_automation_id(
                automation_id=automation_id, limit=limit, offset=offset,
            )
            total = await transaction.automation_history_repository.count_by_automation_id(
                automation_id=automation_id,
            )
        return items, total

    async def dispatch_due_checks(self, batch_size: int) -> dict:
        # Claiming (this transaction) and creating the check Task (task_service's own, separate
        # transaction/session) must not overlap: tasks.automation_id's FK has to lock the very
        # automation row that claim_due_for_dispatch's FOR UPDATE SKIP LOCKED just locked, so
        # holding that lock open across the cross-session INSERT deadlocks the two connections
        # against each other. Committing here first, before any task_service call, avoids it.
        async with self.transaction_manager(use_automation_repository=True) as transaction:
            claimed_automations = await transaction.automation_repository.claim_due_for_dispatch(
                now=datetime.now(tz=timezone.utc), limit=batch_size,
            )
            await self.transaction_manager.commit()

        for automation in claimed_automations:
            task = await self.task_service.create_task(
                parse_type=ParseType.PRODUCT_PAGE,
                marketplace=automation.marketplace,
                inputs=[automation.input_value],
                priority=DISPATCH_PRIORITY,
                ttl=DISPATCH_TTL,
                user_id=automation.user_id,
                result_limit=CHECK_TASK_RESULT_LIMIT,
                automation_id=automation.id,
            )
            async with self.transaction_manager(use_automation_repository=True) as transaction:
                await transaction.automation_repository.set_pending_task(
                    automation_id=automation.id, task_id=task.id,
                )
                await self.transaction_manager.commit()
        return {'dispatched': len(claimed_automations)}

    async def process_pending_results(self, batch_size: int) -> dict:
        async with self.transaction_manager(
            use_automation_repository=True,
            use_automation_history_repository=True,
        ) as transaction:
            awaiting_automations = await transaction.automation_repository.get_awaiting_result(
                limit=batch_size,
            )

            processed_count = 0
            changes_detected_count = 0
            for automation in awaiting_automations:
                task = await self.task_service.get_task_by_id(task_id=automation.pending_task_id)
                if task.status not in (
                    TaskStatus.SUCCEEDED,
                    TaskStatus.FAILED,
                    TaskStatus.EXPIRED,
                    TaskStatus.CANCELLED,
                ):
                    continue

                changes_detected_count += await self._finalize_check(
                    transaction=transaction, automation=automation, task_status=task.status,
                )
                processed_count += 1
            await self.transaction_manager.commit()
        return {'processed': processed_count, 'changes_detected': changes_detected_count}

    async def _finalize_check(
        self,
        transaction: AsyncTransactionManager,
        automation: AutomationEntity,
        task_status: TaskStatus,
    ) -> int:
        changes_detected_count = 0
        last_check_error = None
        baseline_updates: dict[str, int] = {}

        if task_status == TaskStatus.SUCCEEDED:
            results, _ = await self.result_service.get_results_for_task(
                task_id=automation.pending_task_id, limit=CHECK_TASK_RESULT_LIMIT, offset=0,
            )
            if results:
                payload = ProductPagePayload.model_validate(results[0].payload)
                changes, baseline_updates = self._diff_prices(automation=automation, payload=payload)
                if changes:
                    await transaction.automation_history_repository.create(
                        entity=AutomationHistoryEntity(
                            automation_id=automation.id,
                            changes=changes,
                            threshold_breached=any(
                                change['threshold_breached'] for change in changes
                            ),
                        ),
                    )
                    changes_detected_count = 1
        else:
            last_check_error = f'check_task_{task_status.value.lower()}'

        await transaction.automation_repository.finalize_check(
            automation_id=automation.id,
            last_checked_at=datetime.now(tz=timezone.utc),
            last_check_error=last_check_error,
            baseline_updates=baseline_updates,
        )
        return changes_detected_count

    def _diff_prices(
        self,
        automation: AutomationEntity,
        payload: ProductPagePayload,
    ) -> tuple[list[dict], dict[str, int]]:
        """First check for the automation (no baseline yet) seeds the baseline from the current
        prices and records no history. Every later check compares against that fixed baseline —
        not the previous check — per the domain's "reference point" semantics: the baseline only
        moves when the user explicitly updates it via `update_baseline`. Every field that changed
        in this one check is collected into a single list — the caller writes at most one
        `AutomationHistory` row per check, not one row per changed field."""

        baseline_updates: dict[str, int] = {}
        changes: list[dict] = []

        for field, baseline_attribute, payload_attribute in TRACKED_PRICE_FIELDS:
            new_value = getattr(payload, payload_attribute)
            if new_value is None:
                continue

            baseline_value = getattr(automation, baseline_attribute)
            if baseline_value is None:
                baseline_updates[baseline_attribute] = new_value
                continue

            if new_value == baseline_value:
                continue

            threshold_price = baseline_value * (100 - automation.price_drop_threshold_percent) / 100
            changes.append(
                {
                    'field': field.value,
                    'old_value': baseline_value,
                    'new_value': new_value,
                    'threshold_breached': new_value <= threshold_price,
                },
            )

        return changes, baseline_updates

    async def sweep_history_retention(self) -> int:
        async with self.transaction_manager(use_automation_history_repository=True) as transaction:
            deleted_count = await transaction.automation_history_repository.delete_expired()
            await self.transaction_manager.commit()
        return deleted_count
