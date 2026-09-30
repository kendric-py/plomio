from fastapi import Depends, HTTPException, Query, status

from apps.api.src.routers.dependencies import get_date_range
from apps.api.src.routers.schema import DateRange
from packages.automation.src.entities import AutomationListFilters
from packages.automation.src.enums import AutomationStatus


def get_automation_filters(
    automation_status: AutomationStatus | None = Query(
        default=None, alias='status', description='Фильтр по статусу автоматизации',
    ),
    in_stock: bool | None = Query(
        default=None, description='Фильтр по наличию товара (по последней проверке)',
    ),
    price_from: int | None = Query(
        default=None, ge=0, description='Текущая цена от, в копейках (включительно)',
    ),
    price_to: int | None = Query(
        default=None, ge=0, description='Текущая цена до, в копейках (включительно)',
    ),
    date_range: DateRange = Depends(get_date_range),
) -> AutomationListFilters:
    """Опциональные фильтры списка автоматизаций — общие для `GET /` и `GET /with-history`."""
    if price_from is not None and price_to is not None and price_from > price_to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail='price_from must not be greater than price_to',
        )
    return AutomationListFilters(
        status=automation_status,
        in_stock=in_stock,
        price_from=price_from,
        price_to=price_to,
        date_from=date_range.date_from,
        date_to=date_range.date_to,
    )
