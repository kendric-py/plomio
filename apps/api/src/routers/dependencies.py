from datetime import datetime, timezone

from fastapi import HTTPException, Query, status

from apps.api.src.routers.schema import DateRange


def _to_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(tz=timezone.utc)


def get_date_range(
    date_from: datetime | None = Query(
        default=None, description='Начало периода (включительно), ISO8601; без часового пояса — UTC',
    ),
    date_to: datetime | None = Query(
        default=None, description='Конец периода (включительно), ISO8601; без часового пояса — UTC',
    ),
) -> DateRange:
    """Общий опциональный фильтр по датам для списочных ручек, подключается через `Depends`."""
    date_from = _to_utc(date_from)
    date_to = _to_utc(date_to)
    if date_from is not None and date_to is not None and date_from > date_to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail='date_from must not be later than date_to',
        )
    return DateRange(date_from=date_from, date_to=date_to)
