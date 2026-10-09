from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import Select, case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import ObjectNotFoundError
from core.repository import BaseRepository
from packages.task.src.entities import AdminTaskFilters, TaskEntity, TaskItemEntity
from packages.task.src.enums import TaskItemStatus, TaskPurpose, TaskStatus
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
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> list[TaskEntity]:
        statement = self._apply_user_filters(
            statement=select(self.model),
            user_id=user_id,
            status=status,
            include_automation_tasks=include_automation_tasks,
            date_from=date_from,
            date_to=date_to,
        )
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
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> int:
        statement = self._apply_user_filters(
            statement=select(func.count(self.model.id)),
            user_id=user_id,
            status=status,
            include_automation_tasks=include_automation_tasks,
            date_from=date_from,
            date_to=date_to,
        )
        return await self.session.scalar(statement)

    def _apply_user_filters(
        self,
        statement: Select,
        user_id: int,
        status: Optional[TaskStatus],
        include_automation_tasks: bool,
        date_from: Optional[datetime],
        date_to: Optional[datetime],
    ) -> Select:
        """Общие фильтры списка задач пользователя — для выборки и count, чтобы не разъезжались.
        Период фильтрует `created_at`."""
        statement = statement.where(self.model.user_id == user_id)
        if status is not None:
            statement = statement.where(self.model.status == status)
        if not include_automation_tasks:
            statement = statement.where(self.model.automation_id.is_(None))
        if date_from is not None:
            statement = statement.where(self.model.created_at >= date_from)
        if date_to is not None:
            statement = statement.where(self.model.created_at <= date_to)
        return statement

    async def get_page(
        self,
        filters: AdminTaskFilters,
        limit: int,
        offset: int,
    ) -> list[TaskEntity]:
        statement = self._apply_admin_filters(statement=select(self.model), filters=filters)
        statement = (
            statement.order_by(self.model.created_at.desc(), self.model.id)
            .limit(limit)
            .offset(offset)
        )
        database_objects = await self.session.scalars(statement)
        return self._to_entities(database_objects=database_objects)

    async def count_by_filters(self, filters: AdminTaskFilters) -> int:
        statement = self._apply_admin_filters(
            statement=select(func.count(self.model.id)), filters=filters,
        )
        return await self.session.scalar(statement)

    def _apply_admin_filters(self, statement: Select, filters: AdminTaskFilters) -> Select:
        """Общие фильтры админского списка — для выборки и count, чтобы не разъезжались."""
        if filters.task_id is not None:
            statement = statement.where(self.model.id == filters.task_id)
        if filters.item_id is not None:
            statement = statement.where(
                self.model.id.in_(
                    select(TaskItem.task_id).where(TaskItem.id == filters.item_id),
                ),
            )
        if filters.automation_id is not None:
            statement = statement.where(self.model.automation_id == filters.automation_id)
        if filters.purpose == TaskPurpose.TASK:
            statement = statement.where(self.model.automation_id.is_(None))
        elif filters.purpose == TaskPurpose.AUTOMATION:
            statement = statement.where(self.model.automation_id.is_not(None))
        if filters.user_id is not None:
            statement = statement.where(self.model.user_id == filters.user_id)
        if filters.marketplace is not None:
            statement = statement.where(self.model.marketplace == filters.marketplace)
        if filters.status is not None:
            statement = statement.where(self.model.status == filters.status)
        if filters.parse_type is not None:
            statement = statement.where(self.model.parse_type == filters.parse_type)
        if filters.date_from is not None:
            statement = statement.where(self.model.created_at >= filters.date_from)
        if filters.date_to is not None:
            statement = statement.where(self.model.created_at <= filters.date_to)
        return statement

    async def count_grouped_by_status(
        self,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> list[tuple[TaskStatus, bool, int]]:
        """Сводка для админки: `(status, is_automation, count)` по задачам за период (`created_at`).
        Один `GROUP BY` вместо запроса на каждый статус."""
        is_automation = self.model.automation_id.is_not(None)
        statement = select(self.model.status, is_automation, func.count(self.model.id)).group_by(
            self.model.status, is_automation,
        )
        if date_from is not None:
            statement = statement.where(self.model.created_at >= date_from)
        if date_to is not None:
            statement = statement.where(self.model.created_at <= date_to)
        rows = await self.session.execute(statement)
        return [(row[0], bool(row[1]), row[2]) for row in rows]

    async def reset_for_restart(self, task_id: UUID, queue_expires_at: datetime) -> TaskEntity:
        """Возвращает задачу в очередь: `QUEUED` + новый дедлайн, сброс финала, ошибки и аренды.
        Сырой `UPDATE`, так как `BaseRepository.update` игнорирует `None` и не умеет обнулять."""
        statement = (
            update(self.model)
            .where(self.model.id == task_id)
            .values(
                status=TaskStatus.QUEUED,
                queue_expires_at=queue_expires_at,
                error_reason=None,
                finished_at=None,
                claimed_by=None,
                claimed_at=None,
                lease_expires_at=None,
            )
            .returning(self.model)
        )
        database_object = await self.session.scalar(statement)
        if database_object is None:
            raise ObjectNotFoundError
        return self._to_entity(database_object=database_object)

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

    async def get_failed_by_task_ids(
        self, task_ids: list[UUID], per_task_limit: int = 3,
    ) -> dict[UUID, list[TaskItemEntity]]:
        """Упавшие элементы (`FAILED`) задач — для админского списка: оригинальная причина ошибки
        лежит в `TaskItem.error_reason`, а не в `Task.error_reason` (там только `item_failed`).
        Не больше `per_task_limit` на задачу, по порядку входов."""
        if not task_ids:
            return {}

        statement = (
            select(self.model)
            .where(self.model.task_id.in_(task_ids), self.model.status == TaskItemStatus.FAILED)
            .order_by(self.model.task_id, self.model.position)
        )
        database_objects = await self.session.scalars(statement)
        failed_by_task_id: dict[UUID, list[TaskItemEntity]] = {}
        for item in self._to_entities(database_objects=database_objects):
            task_items = failed_by_task_id.setdefault(item.task_id, [])
            if len(task_items) < per_task_limit:
                task_items.append(item)
        return failed_by_task_id

    async def reset_failed_items(self, task_id: UUID) -> int:
        """`FAILED` → `PENDING` с очисткой ошибки (курсор и `result_count` сохраняются — воркер
        продолжит с места). Сырой `UPDATE`: `BaseRepository.update` не умеет обнулять поле."""
        statement = (
            update(self.model)
            .where(self.model.task_id == task_id, self.model.status == TaskItemStatus.FAILED)
            .values(status=TaskItemStatus.PENDING, error_reason=None)
        )
        result = await self.session.execute(statement)
        return result.rowcount

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
