from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from core.enums import Marketplace
from core.exceptions import ObjectNotFoundError
from core.transaction_manager import AsyncTransactionManager
from packages.billing.src.enums import PricingDimension, ReferenceType
from packages.billing.src.exceptions import InsufficientCreditsError
from packages.billing.src.service import BillingService
from packages.notifications.src.service import NotificationService
from packages.task.src.entities import TaskEntity, TaskItemEntity
from packages.task.src.enums import ParseType, TaskItemStatus, TaskStatus
from packages.task.src.exceptions import (
    InvalidTaskTransitionError,
    TaskItemNotExcludableError,
)

PAUSABLE_STATUSES = (TaskStatus.QUEUED, TaskStatus.RUNNING)
CANCELLABLE_STATUSES = (TaskStatus.QUEUED, TaskStatus.PAUSED, TaskStatus.RUNNING)
ACTIVE_ITEM_STATUSES = (TaskItemStatus.PENDING, TaskItemStatus.FAILED)
TERMINAL_ITEM_STATUSES = (TaskItemStatus.SUCCEEDED, TaskItemStatus.FAILED, TaskItemStatus.EXCLUDED)


class TaskService:
    def __init__(
        self,
        transaction_manager: AsyncTransactionManager,
        billing_service: BillingService,
        notification_service: NotificationService,
        frontend_base_url: str = '',
    ):
        self.transaction_manager = transaction_manager
        self.billing_service = billing_service
        self.notification_service = notification_service
        self.frontend_base_url = frontend_base_url

    async def create_task(
        self,
        parse_type: ParseType,
        marketplace: Marketplace,
        inputs: list[str],
        priority: int,
        ttl: timedelta,
        user_id: int,
        result_limit: int | None = None,
        automation_id: UUID | None = None,
        pricing_dimension_code: str | None = None,
        pricing_dimension_value: int | None = None,
    ) -> TaskEntity:
        # automation_id is None <=> a regular user-initiated task (not an automation's check task,
        # which packages.automation.src.service.AutomationService.dispatch_due_checks creates with
        # its own pricing_dimension_code/value already set) — see packages/billing/AGENTS.md,
        # "Интеграция с packages/task/packages/automation".
        if pricing_dimension_code is None and pricing_dimension_value is None:
            pricing_dimension_code = PricingDimension.TASK_PRIORITY.value
            pricing_dimension_value = priority

        if automation_id is None:
            if not await self.billing_service.has_positive_balance(user_id=user_id):
                raise InsufficientCreditsError

        async with self.transaction_manager(
            use_task_repository=True,
            use_task_item_repository=True,
        ) as transaction:
            created_task = await transaction.task_repository.create(
                entity=TaskEntity(
                    parse_type=parse_type,
                    marketplace=marketplace,
                    priority=priority,
                    queue_expires_at=datetime.now(tz=timezone.utc) + ttl,
                    result_limit=result_limit,
                    user_id=user_id,
                    automation_id=automation_id,
                    pricing_dimension_code=pricing_dimension_code,
                    pricing_dimension_value=pricing_dimension_value,
                ),
            )
            for position, input_value in enumerate(inputs):
                await transaction.task_item_repository.create(
                    entity=TaskItemEntity(
                        task_id=created_task.id,
                        position=position,
                        input_value=input_value,
                    ),
                )
            await self.transaction_manager.commit()

        if automation_id is None:
            await self.billing_service.charge(
                user_id=user_id,
                action_code='task.create',
                reference_type=ReferenceType.TASK,
                reference_id=str(created_task.id),
            )
        return created_task

    async def cancel_task(self, task_id: UUID, user_id: int) -> TaskEntity:
        async with self.transaction_manager(use_task_repository=True) as transaction:
            task = await transaction.task_repository.get_by_id(entity_id=task_id)
            if task.user_id != user_id:
                raise ObjectNotFoundError
            if task.status not in CANCELLABLE_STATUSES:
                raise InvalidTaskTransitionError

            updated_task = await transaction.task_repository.update(
                entity=TaskEntity(
                    id=task_id,
                    status=TaskStatus.CANCELLED,
                    finished_at=datetime.now(tz=timezone.utc),
                ),
            )
            await self.transaction_manager.commit()
        return updated_task

    async def pause_task(self, task_id: UUID, user_id: int) -> TaskEntity:
        async with self.transaction_manager(use_task_repository=True) as transaction:
            task = await transaction.task_repository.get_by_id(entity_id=task_id)
            if task.user_id != user_id:
                raise ObjectNotFoundError
            if task.status not in PAUSABLE_STATUSES:
                raise InvalidTaskTransitionError

            updated_task = await transaction.task_repository.update(
                entity=TaskEntity(id=task_id, status=TaskStatus.PAUSED),
            )
            await self.transaction_manager.commit()
        return updated_task

    async def pause_task_system(self, task_id: UUID) -> TaskEntity:
        """Internal counterpart of `pause_task`, without the `user_id` ownership check (same
        relationship as `get_task_by_id` vs `get_task_status`) — called by
        `record_item_progress` when a charge drains the user's balance to `<= 0` mid-task. No-op
        (returns the task unchanged) if it's no longer in a pausable status, since this fires as a
        side effect of billing, not a user action that must succeed."""

        async with self.transaction_manager(use_task_repository=True) as transaction:
            task = await transaction.task_repository.get_by_id(entity_id=task_id)
            if task.status not in PAUSABLE_STATUSES:
                return task

            updated_task = await transaction.task_repository.update(
                entity=TaskEntity(id=task_id, status=TaskStatus.PAUSED),
            )
            await self.transaction_manager.commit()
        return updated_task

    async def resume_task(self, task_id: UUID, user_id: int, ttl: timedelta) -> TaskEntity:
        async with self.transaction_manager(use_task_repository=True) as transaction:
            task = await transaction.task_repository.get_by_id(entity_id=task_id)
            if task.user_id != user_id:
                raise ObjectNotFoundError
            if task.status != TaskStatus.PAUSED:
                raise InvalidTaskTransitionError

            # A task auto-paused by record_item_progress for insufficient credits (see
            # pause_task_system) must not be resumable until the balance is topped up — otherwise
            # the worker drains a few more pages before its next cooperative status check, the
            # balance dips further negative, and it pauses again on the very next charge, forever.
            # Only relevant for tasks that were actually running against billed results
            # (automation_id is None — see create_task); automation check tasks never get
            # auto-paused this way in the first place, since dispatch_due_checks already gates on
            # balance before creating them.
            if task.automation_id is None:
                if not await self.billing_service.has_positive_balance(user_id=user_id):
                    raise InsufficientCreditsError

            # queue_expires_at is the deadline claim_next checks; the original one (from
            # create_task) is almost certainly already in the past by the time a task that has
            # already run gets paused and resumed — without pushing it forward here, claim_next
            # would never pick the task back up, and the next expire_stale_queued() sweep would
            # flip it to EXPIRED instead of resuming it.
            updated_task = await transaction.task_repository.update(
                entity=TaskEntity(
                    id=task_id,
                    status=TaskStatus.QUEUED,
                    queue_expires_at=datetime.now(tz=timezone.utc) + ttl,
                ),
            )
            await self.transaction_manager.commit()
        return updated_task

    async def exclude_task_item(self, task_id: UUID, item_id: UUID) -> TaskEntity:
        async with self.transaction_manager(
            use_task_repository=True,
            use_task_item_repository=True,
        ) as transaction:
            item = await transaction.task_item_repository.get_by_id(entity_id=item_id)
            if item.task_id != task_id:
                raise ObjectNotFoundError
            if item.status != TaskItemStatus.FAILED:
                raise TaskItemNotExcludableError

            await transaction.task_item_repository.update(
                entity=TaskItemEntity(id=item_id, status=TaskItemStatus.EXCLUDED),
            )

            task = await transaction.task_repository.get_by_id(entity_id=task_id)
            items = await transaction.task_item_repository.retrieve_all_by_filter(
                entity=TaskItemEntity(task_id=task_id),
            )
            has_active_items = any(sibling.status in ACTIVE_ITEM_STATUSES for sibling in items)

            if not has_active_items:
                new_status = TaskStatus.SUCCEEDED
            elif task.status == TaskStatus.FAILED:
                # Reviving FAILED -> QUEUED is a resume decision in disguise — same guard as
                # resume_task, and for the same reason: excluding the last bad item off an
                # insufficient-credits task must not be a backdoor around that guard. Checked
                # before commit, so the item exclusion above rolls back too — the user has to
                # retry the exclude once the balance is topped up, same as they'd retry resume.
                if task.automation_id is None:
                    if not await self.billing_service.has_positive_balance(user_id=task.user_id):
                        raise InsufficientCreditsError
                new_status = TaskStatus.QUEUED
            else:
                new_status = None

            updated_task = task
            if new_status is not None:
                update_entity = TaskEntity(id=task_id, status=new_status)
                if new_status == TaskStatus.SUCCEEDED:
                    update_entity.finished_at = datetime.now(tz=timezone.utc)
                updated_task = await transaction.task_repository.update(entity=update_entity)
            await self.transaction_manager.commit()
        return updated_task

    async def record_item_progress(
        self,
        item_id: UUID,
        cursor: dict | None,
        result_count: int,
    ) -> None:
        # result_count is the running total the worker has saved for this item so far (not a
        # delta) — see apps/worker_parser/src/runner.py. The delta since the last recorded value is
        # what's actually new since the last charge, so it's what gets billed here.
        async with self.transaction_manager(
            use_task_repository=True,
            use_task_item_repository=True,
        ) as transaction:
            item = await transaction.task_item_repository.get_by_id(entity_id=item_id)
            delta = result_count - (item.result_count or 0)

            updated_item = await transaction.task_item_repository.update(
                entity=TaskItemEntity(id=item_id, cursor=cursor, result_count=result_count),
            )

            task = None
            if delta > 0:
                task = await transaction.task_repository.get_by_id(entity_id=updated_item.task_id)
            await self.transaction_manager.commit()

        if task is None:
            return

        await self.billing_service.charge(
            user_id=task.user_id,
            action_code=f'result.{task.parse_type.value}',
            quantity=delta,
            dimension_code=task.pricing_dimension_code,
            dimension_value=task.pricing_dimension_value,
            reference_type=ReferenceType.TASK,
            reference_id=str(task.id),
        )
        if not await self.billing_service.has_positive_balance(user_id=task.user_id):
            await self.pause_task_system(task_id=task.id)

    async def complete_item(
        self,
        item_id: UUID,
        status: TaskItemStatus,
        error_reason: str | None = None,
    ) -> None:
        async with self.transaction_manager(
            use_task_repository=True,
            use_task_item_repository=True,
        ) as transaction:
            item = await transaction.task_item_repository.get_by_id(entity_id=item_id)
            # Serializes concurrently completing siblings of the same task (worker_parser now
            # processes TaskItems within a task in parallel) — without this lock, two items
            # finishing at nearly the same time can each see the other as still pending and
            # neither ever flips the parent Task to its terminal status.
            locked_task = await transaction.task_repository.lock_by_id(entity_id=item.task_id)

            completed_item = await transaction.task_item_repository.update(
                entity=TaskItemEntity(id=item_id, status=status, error_reason=error_reason),
            )

            items = await transaction.task_item_repository.retrieve_all_by_filter(
                entity=TaskItemEntity(task_id=completed_item.task_id),
            )
            if any(sibling.status not in TERMINAL_ITEM_STATUSES for sibling in items):
                await self.transaction_manager.commit()
                return

            has_failed_items = any(sibling.status == TaskItemStatus.FAILED for sibling in items)
            final_status = TaskStatus.FAILED if has_failed_items else TaskStatus.SUCCEEDED
            await transaction.task_repository.update(
                entity=TaskEntity(
                    id=completed_item.task_id,
                    status=final_status,
                    error_reason='item_failed' if has_failed_items else None,
                    finished_at=datetime.now(tz=timezone.utc),
                ),
            )
            await self.transaction_manager.commit()

        # automation_id is not None <=> this is an automation's internal check task (see
        # packages/automation/AGENTS.md) — its completion already drives
        # AutomationService._finalize_check's own automation.change_detected event, so emitting
        # task.completed/task.failed here too would duplicate the notification for the same tick.
        if locked_task.automation_id is None:
            await self.notification_service.notify(
                user_id=locked_task.user_id,
                event_code=(
                    'task.completed' if final_status == TaskStatus.SUCCEEDED else 'task.failed'
                ),
                payload={
                    'task_id': str(completed_item.task_id),
                    'error_reason': 'item_failed' if has_failed_items else None,
                    'task_link': (
                        f'{self.frontend_base_url}/tasks/{completed_item.task_id}'
                        if self.frontend_base_url else None
                    ),
                    'result_count': sum(sibling.result_count or 0 for sibling in items),
                },
            )

    async def get_progress(self, task_id: UUID) -> dict:
        async with self.transaction_manager(use_task_item_repository=True) as transaction:
            items = await transaction.task_item_repository.retrieve_all_by_filter(
                entity=TaskItemEntity(task_id=task_id),
            )
        return {
            'total_items': len(items),
            'processed_items': sum(1 for item in items if item.status in TERMINAL_ITEM_STATUSES),
            'result_count': sum(item.result_count or 0 for item in items),
        }

    async def get_task_status(self, task_id: UUID, user_id: int) -> dict:
        async with self.transaction_manager(
            use_task_repository=True,
            use_task_item_repository=True,
        ) as transaction:
            task = await transaction.task_repository.get_by_id(entity_id=task_id)
            if task.user_id != user_id:
                raise ObjectNotFoundError

            items = await transaction.task_item_repository.retrieve_all_by_filter(
                entity=TaskItemEntity(task_id=task_id),
            )
        return {
            'task': task,
            'progress': {
                'total_items': len(items),
                'processed_items': sum(
                    1 for item in items if item.status in TERMINAL_ITEM_STATUSES
                ),
                'result_count': sum(item.result_count or 0 for item in items),
            },
        }

    async def claim_next(
        self,
        worker_id: str,
        lease_duration: timedelta,
    ) -> Optional[TaskEntity]:
        async with self.transaction_manager(use_task_repository=True) as transaction:
            claimed_task = await transaction.task_repository.claim_next(
                worker_id=worker_id,
                lease_duration=lease_duration,
            )
            await self.transaction_manager.commit()
        return claimed_task

    async def heartbeat(
        self,
        task_id: UUID,
        worker_id: str,
        lease_duration: timedelta,
    ) -> None:
        async with self.transaction_manager(use_task_repository=True) as transaction:
            await transaction.task_repository.heartbeat(
                task_id=task_id,
                worker_id=worker_id,
                lease_duration=lease_duration,
            )
            await self.transaction_manager.commit()

    async def expire_stale_queued(self) -> int:
        async with self.transaction_manager(use_task_repository=True) as transaction:
            expired_count = await transaction.task_repository.expire_stale_queued()
            await self.transaction_manager.commit()
        return expired_count

    async def reclaim_expired_leases(self, requeue_ttl: timedelta) -> int:
        async with self.transaction_manager(use_task_repository=True) as transaction:
            reclaimed_count = await transaction.task_repository.reclaim_expired_leases(
                requeue_ttl=requeue_ttl,
            )
            await self.transaction_manager.commit()
        return reclaimed_count

    async def get_task_by_id(self, task_id: UUID) -> TaskEntity:
        async with self.transaction_manager(use_task_repository=True) as transaction:
            return await transaction.task_repository.get_by_id(entity_id=task_id)

    async def get_tasks_by_ids(self, task_ids: list[UUID]) -> list[TaskEntity]:
        """Batched counterpart of `get_task_by_id` — one query for a whole set of task ids instead
        of one per id (used by `AutomationService.process_pending_results` to avoid an N+1 lookup
        per awaiting automation in the same result-sweep batch)."""

        async with self.transaction_manager(use_task_repository=True) as transaction:
            return await transaction.task_repository.get_by_ids(entity_ids=task_ids)

    async def get_task_items(self, task_id: UUID) -> list[TaskItemEntity]:
        async with self.transaction_manager(use_task_item_repository=True) as transaction:
            return await transaction.task_item_repository.retrieve_all_by_filter(
                entity=TaskItemEntity(task_id=task_id),
            )

    async def list_tasks(
        self,
        user_id: int,
        limit: int,
        offset: int,
        status: Optional[TaskStatus] = None,
        include_automation_tasks: bool = False,
    ) -> tuple[list[dict], int]:
        async with self.transaction_manager(
            use_task_repository=True,
            use_task_item_repository=True,
        ) as transaction:
            tasks = await transaction.task_repository.get_by_user_id(
                user_id=user_id,
                limit=limit,
                offset=offset,
                status=status,
                include_automation_tasks=include_automation_tasks,
            )
            total = await transaction.task_repository.count_by_user_id(
                user_id=user_id, status=status, include_automation_tasks=include_automation_tasks,
            )
            progress_by_task_id = await transaction.task_item_repository.get_progress_by_task_ids(
                task_ids=[task.id for task in tasks],
            )

        empty_progress = {'total_items': 0, 'processed_items': 0, 'result_count': 0}
        items = [
            {
                **task.model_dump(),
                **progress_by_task_id.get(task.id, empty_progress),
            }
            for task in tasks
        ]
        return items, total

    async def ensure_task_owner(self, task_id: UUID, user_id: int) -> TaskEntity:
        async with self.transaction_manager(use_task_repository=True) as transaction:
            task = await transaction.task_repository.get_by_id(entity_id=task_id)
            if task.user_id != user_id:
                raise ObjectNotFoundError
            return task

    async def delete_task(self, task_id: UUID, user_id: int) -> None:
        async with self.transaction_manager(use_task_repository=True) as transaction:
            task = await transaction.task_repository.get_by_id(entity_id=task_id)
            if task.user_id != user_id:
                raise ObjectNotFoundError

            await transaction.task_repository.delete(entity_id=task_id)
            await self.transaction_manager.commit()
