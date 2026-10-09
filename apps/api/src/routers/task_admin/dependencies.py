from uuid import UUID

from fastapi import Depends, Query

from apps.api.src.routers.dependencies import get_date_range
from apps.api.src.routers.schema import DateRange
from core.enums import Marketplace
from packages.task.src.entities import AdminTaskFilters
from packages.task.src.enums import ParseType, TaskPurpose, TaskStatus


def get_admin_task_filters(
    task_id: UUID | None = Query(default=None, description='ID задачи'),
    item_id: UUID | None = Query(default=None, description='ID элемента — найдёт его задачу'),
    automation_id: UUID | None = Query(
        default=None, description='ID автоматизации — её проверочные задачи',
    ),
    purpose: TaskPurpose | None = Query(
        default=None, description='task — пользовательская, automation — проверка автоматизации',
    ),
    user_id: int | None = Query(default=None, description='Автор задачи'),
    marketplace: Marketplace | None = Query(default=None, description='Маркетплейс'),
    task_status: TaskStatus | None = Query(
        default=None, alias='status', description='Статус задачи',
    ),
    parse_type: ParseType | None = Query(default=None, description='Тип парсинга'),
    date_range: DateRange = Depends(get_date_range),
) -> AdminTaskFilters:
    """Опциональные фильтры админского списка задач; AND, период — по `created_at`."""
    return AdminTaskFilters(
        task_id=task_id,
        item_id=item_id,
        automation_id=automation_id,
        purpose=purpose,
        user_id=user_id,
        marketplace=marketplace,
        status=task_status,
        parse_type=parse_type,
        date_from=date_range.date_from,
        date_to=date_range.date_to,
    )
