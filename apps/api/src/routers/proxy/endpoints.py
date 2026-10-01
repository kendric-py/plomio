from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Query, status

from apps.api.src.container import DependencyContainer
from apps.api.src.routers.billing.dependencies import get_current_admin_user
from apps.api.src.routers.proxy.dependencies import verify_worker_token
from apps.api.src.routers.proxy.schema import (
    CreateProxyRequest,
    IssuedProxyResponse,
    ProxyListResponse,
    ProxyResponse,
    UpdateProxyRequest,
)
from apps.api.src.routers.schema import PaginationMeta
from core.exceptions import DuplicatedObjectError, ObjectNotFoundError
from packages.proxy.src.entities import ProxyEntity
from packages.proxy.src.enums import ProxyType
from packages.proxy.src.service import ProxyService
from packages.user.src.entities import UserEntity

router = APIRouter(prefix='/proxy', tags=['Proxy'])
admin_router = APIRouter(prefix='/admin/proxies', tags=['Proxy Admin'])


def _to_response(proxy: ProxyEntity) -> ProxyResponse:
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
        proxy_type=proxy.proxy_type.value,
        proxy_host=proxy.host,
        proxy_port=proxy.port,
        proxy_username=proxy.username,
        proxy_password=proxy.password,
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
        items=[_to_response(proxy=proxy) for proxy in proxies],
        meta=PaginationMeta(total=total, limit=limit, offset=offset),
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
    return _to_response(proxy=proxy)


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
    return _to_response(proxy=proxy)


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
