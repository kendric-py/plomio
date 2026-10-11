from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import Depends, HTTPException, Query, status

from apps.api.src.config import config
from apps.api.src.routers.automation.schema import AutomationResponse
from apps.api.src.routers.automation_admin.schema import (
    AdminAutomationItemResponse,
    AdminAutomationResponse,
)
from apps.api.src.routers.dependencies import get_date_range
from apps.api.src.routers.schema import DateRange
from core.enums import Marketplace
from packages.automation.src.entities import AdminAutomationFilters, AutomationEntity
from packages.automation.src.enums import AutomationStatus


OVERDUE_GRACE_DISPATCH_TICKS = 3


def get_overdue_grace() -> timedelta:
    """Допуск просрочки — три тика диспетчера: срок проверки, опоздавший меньше чем на это время,
    ещё в обычной очереди на отправку, а не просрочен."""
    return timedelta(seconds=OVERDUE_GRACE_DISPATCH_TICKS * config.AUTOMATION.DISPATCH_INTERVAL_SECONDS)


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
        overdue_grace=get_overdue_grace(),
        has_error=has_error,
        search=search.strip() if search and search.strip() else None,
        date_from=date_range.date_from,
        date_to=date_range.date_to,
    )


def automation_not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Automation not found')


def is_overdue(automation: AutomationEntity, grace: timedelta) -> bool:
    return (
        automation.status == AutomationStatus.ACTIVE
        and automation.pending_task_id is None
        and automation.next_check_at <= datetime.now(tz=timezone.utc) - grace
    )


def build_item_response(
    automation: AutomationEntity, grace: timedelta,
) -> AdminAutomationItemResponse:
    return AdminAutomationItemResponse(
        **AutomationResponse.model_validate(obj=automation, from_attributes=True).model_dump(),
        user_id=automation.user_id,
        pending_task_id=automation.pending_task_id,
        is_overdue=is_overdue(automation=automation, grace=grace),
    )


def build_detail_response(
    automation: AutomationEntity, last_info: dict | None, grace: timedelta,
) -> AdminAutomationResponse:
    return AdminAutomationResponse(
        **AutomationResponse.model_validate(obj=automation, from_attributes=True).model_dump(),
        last_info=last_info,
        user_id=automation.user_id,
        pending_task_id=automation.pending_task_id,
        is_overdue=is_overdue(automation=automation, grace=grace),
    )
