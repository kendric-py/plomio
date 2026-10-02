from datetime import datetime, timedelta, timezone

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


MAX_CHART_PERIOD = timedelta(days=365)


def get_chart_period(
    days: int = Query(
        default=30, ge=1, le=365,
        description='Период графика в днях, заканчивающийся в date_to (или сейчас); игнорируется, '
        'если задан date_from',
    ),
    date_range: DateRange = Depends(get_date_range),
) -> DateRange:
    """Диапазон графика: `date_from`/`date_to` (зум) либо последние `days` дней. Конец не позже
    "сейчас" (будущего на графике нет), длина — не больше года. Возвращает `DateRange` с обеими
    границами заданными."""
    now = datetime.now(tz=timezone.utc)
    date_to = min(date_range.date_to or now, now)
    date_from = date_range.date_from or date_to - timedelta(days=days)
    if date_from >= date_to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail='date_from must be earlier than date_to (and not in the future)',
        )
    if date_to - date_from > MAX_CHART_PERIOD:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail='chart period must not exceed 365 days',
        )
    return DateRange(date_from=date_from, date_to=date_to)
