from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from core.enums import Marketplace
from core.exceptions import ObjectNotFoundError
from core.transaction_manager import AsyncTransactionManager
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
    def __init__(self, transaction_manager: AsyncTransactionManager):
        self.transaction_manager = transaction_manager

    async def create_task(
        self,
        parse_type: ParseType,
        marketplace: Marketplace,
        inputs: list[str],
        priority: int,
        ttl: timedelta,
        user_id: int,
        result_limit: int | None = None,
    ) -> TaskEntity:
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
        return created_task

    async def cancel_task(self, task_id: UUID) -> TaskEntity:
        async with self.transaction_manager(use_task_repository=True) as transaction:
            task = await transaction.task_repository.get_by_id(entity_id=task_id)
            if task.status not in CANCELLABLE_STATUSES:
                raise InvalidTaskTransitionError

            updated_task = await transaction.task_repository.update(
                entity=TaskEntity(id=task_id, status=TaskStatus.CANCELLED),
            )
            await self.transaction_manager.commit()
        return updated_task

    async def pause_task(self, task_id: UUID) -> TaskEntity:
        async with self.transaction_manager(use_task_repository=True) as transaction:
            task = await transaction.task_repository.get_by_id(entity_id=task_id)
            if task.status not in PAUSABLE_STATUSES:
                raise InvalidTaskTransitionError

            updated_task = await transaction.task_repository.update(
                entity=TaskEntity(id=task_id, status=TaskStatus.PAUSED),
            )
            await self.transaction_manager.commit()
        return updated_task

    async def resume_task(self, task_id: UUID) -> TaskEntity:
        async with self.transaction_manager(use_task_repository=True) as transaction:
            task = await transaction.task_repository.get_by_id(entity_id=task_id)
            if task.status != TaskStatus.PAUSED:
                raise InvalidTaskTransitionError

            updated_task = await transaction.task_repository.update(
                entity=TaskEntity(id=task_id, status=TaskStatus.QUEUED),
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
                new_status = TaskStatus.QUEUED
            else:
                new_status = None

            updated_task = task
            if new_status is not None:
                updated_task = await transaction.task_repository.update(
                    entity=TaskEntity(id=task_id, status=new_status),
                )
            await self.transaction_manager.commit()
        return updated_task

    async def record_item_progress(
        self,
        item_id: UUID,
        cursor: dict | None,
        result_count: int,
    ) -> None:
        async with self.transaction_manager(use_task_item_repository=True) as transaction:
            await transaction.task_item_repository.update(
                entity=TaskItemEntity(id=item_id, cursor=cursor, result_count=result_count),
            )
            await self.transaction_manager.commit()

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
            await transaction.task_repository.update(
                entity=TaskEntity(
                    id=completed_item.task_id,
                    status=TaskStatus.FAILED if has_failed_items else TaskStatus.SUCCEEDED,
                    error_reason='item_failed' if has_failed_items else None,
                ),
            )
            await self.transaction_manager.commit()

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

    async def reclaim_expired_leases(self) -> int:
        async with self.transaction_manager(use_task_repository=True) as transaction:
            reclaimed_count = await transaction.task_repository.reclaim_expired_leases()
            await self.transaction_manager.commit()
        return reclaimed_count

    async def get_task_by_id(self, task_id: UUID) -> TaskEntity:
        async with self.transaction_manager(use_task_repository=True) as transaction:
            return await transaction.task_repository.get_by_id(entity_id=task_id)

    async def get_task_items(self, task_id: UUID) -> list[TaskItemEntity]:
        async with self.transaction_manager(use_task_item_repository=True) as transaction:
            return await transaction.task_item_repository.retrieve_all_by_filter(
                entity=TaskItemEntity(task_id=task_id),
            )

    async def ensure_task_owner(self, task_id: UUID, user_id: int) -> TaskEntity:
        async with self.transaction_manager(use_task_repository=True) as transaction:
            task = await transaction.task_repository.get_by_id(entity_id=task_id)
            if task.user_id != user_id:
                raise ObjectNotFoundError
            return task
