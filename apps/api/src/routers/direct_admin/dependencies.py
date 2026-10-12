from fastapi import Depends, Query

from apps.api.src.routers.dependencies import get_date_range
from apps.api.src.routers.direct_admin.schema import (
    DirectOutcomeCount,
    DirectSummaryResponse,
    DirectTypeCount,
)
from apps.api.src.routers.schema import DateRange
from core.enums import Marketplace
from packages.direct.src.entities import DirectRequestFilters, DirectSummaryEntity
from packages.direct.src.enums import DirectOutcome, DirectRequestType


def get_direct_request_filters(
    user_id: int | None = Query(default=None, description='Пользователь'),
    marketplace: Marketplace | None = Query(default=None, description='Маркетплейс'),
    request_type: DirectRequestType | None = Query(default=None, description='Тип запроса'),
    outcome: DirectOutcome | None = Query(default=None, description='Итог запроса'),
    proxy_id: int | None = Query(default=None, description='Прокси сессии воркера'),
    search: str | None = Query(
        default=None, max_length=200, description='Подстрока в запросе или точный `request_id`',
    ),
    date_range: DateRange = Depends(get_date_range),
) -> DirectRequestFilters:
    """Опциональные фильтры истории direct-запросов; AND, период — по времени запроса."""
    return DirectRequestFilters(
        user_id=user_id,
        marketplace=marketplace,
        request_type=request_type,
        outcome=outcome,
        proxy_id=proxy_id,
        search=search.strip() if search and search.strip() else None,
        date_from=date_range.date_from,
        date_to=date_range.date_to,
    )


def build_summary_response(summary: DirectSummaryEntity) -> DirectSummaryResponse:
    ok_count = summary.by_outcome.get(DirectOutcome.OK, 0)
    return DirectSummaryResponse(
        total=summary.total,
        success_percent=round(ok_count * 100 / summary.total) if summary.total else 0,
        by_outcome=[
            DirectOutcomeCount(outcome=outcome, count=count)
            for outcome, count in sorted(summary.by_outcome.items(), key=lambda item: -item[1])
        ],
        by_type=[
            DirectTypeCount(request_type=request_type, count=count)
            for request_type, count in sorted(summary.by_type.items(), key=lambda item: -item[1])
        ],
        credits_charged=summary.credits_charged,
        avg_total_ms=summary.avg_total_ms,
        p95_total_ms=summary.p95_total_ms,
    )
