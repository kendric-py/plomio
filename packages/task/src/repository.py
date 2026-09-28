from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import ObjectNotFoundError
from core.repository import BaseRepository
from packages.task.src.entities import TaskEntity, TaskItemEntity
from packages.task.src.enums import TaskItemStatus, TaskStatus
from packages.task.src.models import Task, TaskItem

TERMINAL_ITEM_STATUSES = (TaskItemStatus.SUCCEEDED, TaskItemStatus.FAILED, TaskItemStatus.EXCLUDED)


class TaskRepository(BaseRepository[Task, TaskEntity]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=Task, entity_object=TaskEntity, session=session)

    async def get_by_user_id(
        self,
        user_id: int,
        limit: int,
        offset: int,
        status: Optional[TaskStatus] = None,
        include_automation_tasks: bool = False,
    ) -> list[TaskEntity]:
        statement = select(self.model).where(self.model.user_id == user_id)
        if status is not None:
            statement = statement.where(self.model.status == status)
        if not include_automation_tasks:
            statement = statement.where(self.model.automation_id.is_(None))
        statement = (
            statement.order_by(self.model.created_at.desc()).limit(limit).offset(offset)
        )
        database_objects = await self.session.scalars(statement)
        return self._to_entities(database_objects=database_objects)

    async def count_by_user_id(
        self,
        user_id: int,
        status: Optional[TaskStatus] = None,
        include_automation_tasks: bool = False,
    ) -> int:
        statement = select(func.count(self.model.id)).where(self.model.user_id == user_id)
        if status is not None:
            statement = statement.where(self.model.status == status)
        if not include_automation_tasks:
            statement = statement.where(self.model.automation_id.is_(None))
        return await self.session.scalar(statement)

    async def claim_next(
        self,
        worker_id: str,
        lease_duration: timedelta,
    ) -> Optional[TaskEntity]:
        now = datetime.now(tz=timezone.utc)
        statement = (
            select(self.model)
            .where(self.model.status == TaskStatus.QUEUED, self.model.queue_expires_at > now)
            .order_by(self.model.priority.asc(), self.model.created_at.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        database_object = await self.session.scalar(statement)
        if database_object is None:
            return None

        database_object.status = TaskStatus.RUNNING
        database_object.claimed_by = worker_id
        database_object.claimed_at = now
        database_object.lease_expires_at = now + lease_duration
        if database_object.started_at is None:
            database_object.started_at = now
        await self.session.flush()
        return self._to_entity(database_object=database_object)

    async def expire_stale_queued(self) -> int:
        now = datetime.now(tz=timezone.utc)
        statement = (
            update(self.model)
            .where(self.model.status == TaskStatus.QUEUED, self.model.queue_expires_at <= now)
            .values(status=TaskStatus.EXPIRED)
        )
        result = await self.session.execute(statement)
        return result.rowcount

    async def reclaim_expired_leases(self, requeue_ttl: timedelta) -> int:
        now = datetime.now(tz=timezone.utc)
        statement = (
            update(self.model)
            .where(self.model.status == TaskStatus.RUNNING, self.model.lease_expires_at <= now)
            .values(
                status=TaskStatus.QUEUED,
                claimed_by=None,
                claimed_at=None,
                lease_expires_at=None,
                # Same reasoning as resume_task's queue_expires_at recompute: a reclaimed task may
                # well have run past its original queue_expires_at (set once in create_task) before
                # its worker died, so leaving it untouched would make claim_next never pick it back
                # up and the next expire_stale_queued() sweep would flip it to EXPIRED instead of
                # retrying it.
                queue_expires_at=now + requeue_ttl,
            )
        )
        result = await self.session.execute(statement)
        return result.rowcount

    async def heartbeat(self, task_id: UUID, worker_id: str, lease_duration: timedelta) -> None:
        now = datetime.now(tz=timezone.utc)
        statement = (
            update(self.model)
            .where(self.model.id == task_id, self.model.claimed_by == worker_id)
            .values(lease_expires_at=now + lease_duration)
        )
        await self.session.execute(statement)

    async def get_by_ids(self, entity_ids: list[UUID]) -> list[TaskEntity]:
        if not entity_ids:
            return []

        statement = select(self.model).where(self.model.id.in_(entity_ids))
        database_objects = await self.session.scalars(statement)
        return self._to_entities(database_objects=database_objects)

    async def lock_by_id(self, entity_id: UUID) -> TaskEntity:
        """Row-level lock (`SELECT ... FOR UPDATE`, blocking — not `skip_locked`), held until the
        caller's transaction commits/rolls back. Used by `TaskService.complete_item` to serialize
        concurrently completing sibling `TaskItem`s of the same task — see that method."""

        statement = select(self.model).where(self.model.id == entity_id).with_for_update()
        database_object = await self.session.scalar(statement)
        if database_object is None:
            raise ObjectNotFoundError
        return self._to_entity(database_object=database_object)


class TaskItemRepository(BaseRepository[TaskItem, TaskItemEntity]):
    def __init__(self, session: AsyncSession):
        super().__init__(
            model=TaskItem,
            entity_object=TaskItemEntity,
            session=session,
        )

    async def get_progress_by_task_ids(self, task_ids: list[UUID]) -> dict[UUID, dict]:
        if not task_ids:
            return {}

        is_terminal = self.model.status.in_(TERMINAL_ITEM_STATUSES)
        statement = (
            select(
                self.model.task_id,
                func.count(self.model.id).label('total_items'),
                func.coalesce(func.sum(case((is_terminal, 1), else_=0)), 0).label(
                    'processed_items',
                ),
                func.coalesce(func.sum(self.model.result_count), 0).label('result_count'),
            )
            .where(self.model.task_id.in_(task_ids))
            .group_by(self.model.task_id)
        )
        rows = await self.session.execute(statement)
        return {
            row.task_id: {
                'total_items': row.total_items,
                'processed_items': row.processed_items,
                'result_count': row.result_count,
            }
            for row in rows
        }
