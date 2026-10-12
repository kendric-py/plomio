import secrets

from fastapi import Header, HTTPException, status

from apps.api.src.config import config
from apps.api.src.routers.proxy.schema import (
    GenerationDay,
    GenerationOutcomeShare,
    ProxyGenerationStatsResponse,
    ProxyResponse,
)
from packages.proxy.src.entities import OutcomeCount, OutcomeDayCount, ProxyEntity
from packages.sessions.src.enums import SessionGenerationOutcome
from packages.sessions.src.errors import SESSION_OUTCOME_LABELS


async def verify_worker_token(
    x_worker_token: str | None = Header(default=None, alias='X-Worker-Token'),
) -> None:
    """Авторизация воркеров на ручках `/api/proxy/*` общим секретом `PROXY_WORKER_TOKEN`.
    Пустой токен в конфиге — выдача выключена (503), а не открыта всем."""
    expected_token = config.PROXY.WORKER_TOKEN
    if not expected_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail='Proxy issuing is not configured',
        )
    if x_worker_token is None or not secrets.compare_digest(
        x_worker_token.encode(), expected_token.encode(),
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Invalid worker token',
        )


def build_proxy_response(proxy: ProxyEntity) -> ProxyResponse:
    return ProxyResponse(
        id=proxy.id,
        proxy_type=proxy.proxy_type,
        host=proxy.host,
        port=proxy.port,
        username=proxy.username,
        has_password=bool(proxy.password),
        is_active=proxy.is_active,
        note=proxy.note,
        created_at=proxy.created_at,
        updated_at=proxy.updated_at,
    )


def build_generation_days(day_counts: list[OutcomeDayCount]) -> list[GenerationDay]:
    return [
        GenerationDay(day=item.day, outcome=item.outcome, count=item.count)
        for item in day_counts
    ]


def build_generation_stats(
    proxy_id: int,
    include_antibot: bool,
    outcome_counts: list[OutcomeCount],
    day_counts: list[OutcomeDayCount],
) -> ProxyGenerationStatsResponse:
    total = sum(item.count for item in outcome_counts)
    success_count = sum(
        item.count for item in outcome_counts if item.outcome == SessionGenerationOutcome.SUCCESS
    )
    return ProxyGenerationStatsResponse(
        proxy_id=proxy_id,
        include_antibot=include_antibot,
        total=total,
        success_percent=round(success_count * 100 / total) if total else 0,
        by_outcome=[
            GenerationOutcomeShare(
                outcome=item.outcome,
                label=SESSION_OUTCOME_LABELS[item.outcome],
                count=item.count,
                percent=round(item.count * 100 / total),
            )
            for item in outcome_counts
        ],
        by_day=build_generation_days(day_counts=day_counts),
    )
