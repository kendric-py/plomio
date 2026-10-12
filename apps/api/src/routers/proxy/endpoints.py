from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Query, status

from apps.api.src.container import DependencyContainer
from apps.api.src.routers.billing.dependencies import get_current_admin_user
from apps.api.src.routers.dependencies import get_date_range
from apps.api.src.routers.proxy.dependencies import (
    build_generation_days,
    build_generation_stats,
    build_proxy_response,
    verify_worker_token,
)
from apps.api.src.routers.proxy.schema import (
    AntibotTimelineResponse,
    CreateProxyRequest,
    IssuedProxyResponse,
    ProxyGenerationStatsResponse,
    ProxyListResponse,
    ProxyResponse,
    RecordGenerationRequest,
    UpdateProxyRequest,
)
from apps.api.src.routers.schema import DateRange, PaginationMeta
from core.enums import Marketplace
from core.exceptions import DuplicatedObjectError, ObjectNotFoundError
from packages.proxy.src.enums import ProxyType
from packages.proxy.src.service import ProxyService
from packages.sessions.src.enums import SessionGenerationOutcome
from packages.user.src.entities import UserEntity

router = APIRouter(prefix='/proxy', tags=['Proxy'])
admin_router = APIRouter(prefix='/admin/proxies', tags=['Proxy Admin'])


@router.get('/issue', dependencies=[Depends(verify_worker_token)])
@inject
async def issue_proxy(
    proxy_type: ProxyType | None = Query(default=None, description='Только прокси этого типа'),
    proxy_service: ProxyService = Depends(Provide[DependencyContainer.proxy_service]),
) -> IssuedProxyResponse:
    """Случайный активный прокси для воркера; 404, если подходящих нет."""
    proxy = await proxy_service.issue_random(proxy_type=proxy_type)
    if proxy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='No active proxies available',
        )
    return IssuedProxyResponse(
        proxy_id=proxy.id,
        proxy_type=proxy.proxy_type.value,
        proxy_host=proxy.host,
        proxy_port=proxy.port,
        proxy_username=proxy.username,
        proxy_password=proxy.password,
    )


@router.post(
    '/generations',
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(verify_worker_token)],
)
@inject
async def record_generation(
    body: RecordGenerationRequest,
    proxy_service: ProxyService = Depends(Provide[DependencyContainer.proxy_service]),
) -> None:
    """Воркер сообщает итог попытки генерации сессии (успех или ошибка). Если прокси уже удалён,
    генерация всё равно записывается — без прокси."""
    await proxy_service.record_generation(
        proxy_id=body.proxy_id,
        marketplace=body.marketplace,
        outcome=body.outcome,
        traceback=body.traceback,
    )


@admin_router.get('/')
@inject
async def list_proxies(
    limit: int = Query(default=100, ge=1, le=500, description='Размер страницы'),
    offset: int = Query(default=0, ge=0, description='Смещение страницы'),
    is_active: bool | None = Query(default=None, description='Фильтр по активности'),
    _current_admin: UserEntity = Depends(get_current_admin_user),
    proxy_service: ProxyService = Depends(Provide[DependencyContainer.proxy_service]),
) -> ProxyListResponse:
    proxies, total = await proxy_service.list_page(
        limit=limit, offset=offset, is_active=is_active,
    )
    return ProxyListResponse(
        items=[build_proxy_response(proxy=proxy) for proxy in proxies],
        meta=PaginationMeta(total=total, limit=limit, offset=offset),
    )


@admin_router.get('/antibot-timeline')
@inject
async def get_antibot_timeline(
    marketplace: Marketplace | None = Query(default=None, description='Только этот маркетплейс'),
    date_range: DateRange = Depends(get_date_range),
    _current_admin: UserEntity = Depends(get_current_admin_user),
    proxy_service: ProxyService = Depends(Provide[DependencyContainer.proxy_service]),
) -> AntibotTimelineResponse:
    """Антибот-ошибки генерации по дням (по всем прокси). Рост — признак смены скриптов антибота,
    а не проблемы конкретного прокси. Регистрируется до `/{proxy_id}`."""
    day_counts = await proxy_service.get_antibot_by_day(
        marketplace=marketplace, date_from=date_range.date_from, date_to=date_range.date_to,
    )
    return AntibotTimelineResponse(items=build_generation_days(day_counts=day_counts))


@admin_router.get('/{proxy_id}')
@inject
async def get_proxy(
    proxy_id: int,
    _current_admin: UserEntity = Depends(get_current_admin_user),
    proxy_service: ProxyService = Depends(Provide[DependencyContainer.proxy_service]),
) -> ProxyResponse:
    try:
        proxy = await proxy_service.get_proxy(proxy_id=proxy_id)
    except ObjectNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Proxy not found',
        ) from error
    return build_proxy_response(proxy=proxy)


@admin_router.get('/{proxy_id}/generation-stats')
@inject
async def get_proxy_generation_stats(
    proxy_id: int,
    outcomes: list[SessionGenerationOutcome] | None = Query(
        default=None, description='Только эти итоги (повторяющийся параметр)',
    ),
    include_antibot: bool = Query(
        default=False, description='Учитывать антибот-ошибки (`antibot_init`)',
    ),
    date_range: DateRange = Depends(get_date_range),
    _current_admin: UserEntity = Depends(get_current_admin_user),
    proxy_service: ProxyService = Depends(Provide[DependencyContainer.proxy_service]),
) -> ProxyGenerationStatsResponse:
    """Генерации сессий через прокси: сводка по итогам (круговой график) и по дням."""
    try:
        outcome_counts, day_counts = await proxy_service.get_generation_stats(
            proxy_id=proxy_id,
            date_from=date_range.date_from,
            date_to=date_range.date_to,
            outcomes=outcomes,
            include_antibot=include_antibot,
        )
    except ObjectNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Proxy not found',
        ) from error
    return build_generation_stats(
        proxy_id=proxy_id,
        include_antibot=include_antibot,
        outcome_counts=outcome_counts,
        day_counts=day_counts,
    )


@admin_router.post('/', status_code=status.HTTP_201_CREATED)
@inject
async def create_proxy(
    body: CreateProxyRequest,
    _current_admin: UserEntity = Depends(get_current_admin_user),
    proxy_service: ProxyService = Depends(Provide[DependencyContainer.proxy_service]),
) -> ProxyResponse:
    try:
        proxy = await proxy_service.create_proxy(**body.model_dump())
    except DuplicatedObjectError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Proxy with this type, host, port and username already exists',
        ) from error
    return build_proxy_response(proxy=proxy)


@admin_router.patch('/{proxy_id}')
@inject
async def update_proxy(
    proxy_id: int,
    body: UpdateProxyRequest,
    _current_admin: UserEntity = Depends(get_current_admin_user),
    proxy_service: ProxyService = Depends(Provide[DependencyContainer.proxy_service]),
) -> ProxyResponse:
    try:
        proxy = await proxy_service.update_proxy(
            proxy_id=proxy_id, values=body.changed_fields(),
        )
    except ObjectNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Proxy not found',
        ) from error
    except DuplicatedObjectError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Proxy with this type, host, port and username already exists',
        ) from error
    return build_proxy_response(proxy=proxy)


@admin_router.delete('/{proxy_id}', status_code=status.HTTP_204_NO_CONTENT)
@inject
async def delete_proxy(
    proxy_id: int,
    _current_admin: UserEntity = Depends(get_current_admin_user),
    proxy_service: ProxyService = Depends(Provide[DependencyContainer.proxy_service]),
) -> None:
    try:
        await proxy_service.delete_proxy(proxy_id=proxy_id)
    except ObjectNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Proxy not found',
        ) from error
