from uuid import UUID

from fastapi import Depends, Query

from apps.api.src.routers.dependencies import get_date_range
from apps.api.src.routers.schema import DateRange
from core.enums import Marketplace
from packages.automation.src.entities import AdminAutomationFilters
from packages.automation.src.enums import AutomationStatus


def get_admin_automation_filters(
    automation_id: UUID | None = Query(default=None, description='ID автоматизации'),
    user_id: int | None = Query(default=None, description='Владелец'),
    marketplace: Marketplace | None = Query(default=None, description='Маркетплейс'),
    automation_status: AutomationStatus | None = Query(
        default=None, alias='status', description='Статус автоматизации',
    ),
    in_stock: bool | None = Query(default=None, description='Наличие по последней проверке'),
    overdue: bool | None = Query(default=None, description='true — только просроченные'),
    has_error: bool | None = Query(default=None, description='true — только с ошибкой проверки'),
    search: str | None = Query(
        default=None, max_length=200, description='Подстрока в названии, артикуле или ссылке',
    ),
    date_range: DateRange = Depends(get_date_range),
) -> AdminAutomationFilters:
    """Опциональные фильтры админского списка автоматизаций; AND, период — по `created_at`."""
    return AdminAutomationFilters(
        automation_id=automation_id,
        user_id=user_id,
        marketplace=marketplace,
        status=automation_status,
        in_stock=in_stock,
        overdue=overdue,
        has_error=has_error,
        search=search.strip() if search and search.strip() else None,
        date_from=date_range.date_from,
        date_to=date_range.date_to,
    )
