from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Query

from apps.api.src.container import DependencyContainer
from apps.api.src.routers.billing.dependencies import get_current_admin_user
from apps.api.src.routers.direct_admin.dependencies import (
    build_summary_response,
    get_direct_request_filters,
)
from apps.api.src.routers.direct_admin.schema import (
    DirectRequestListResponse,
    DirectRequestResponse,
    DirectSummaryResponse,
)
from apps.api.src.routers.schema import PaginationMeta
from packages.direct.src.entities import DirectRequestFilters
from packages.direct.src.service import DirectService
from packages.user.src.entities import UserEntity

admin_router = APIRouter(prefix='/admin/direct-requests', tags=['Direct Admin'])


@admin_router.get('/summary')
@inject
async def get_direct_summary(
    filters: DirectRequestFilters = Depends(get_direct_request_filters),
    _current_admin: UserEntity = Depends(get_current_admin_user),
    direct_service: DirectService = Depends(Provide[DependencyContainer.direct_service]),
) -> DirectSummaryResponse:
    return build_summary_response(await direct_service.get_summary(filters=filters))


@admin_router.get('/')
@inject
async def list_direct_requests(
    filters: DirectRequestFilters = Depends(get_direct_request_filters),
    limit: int = Query(default=50, ge=1, le=500, description='Размер страницы'),
    offset: int = Query(default=0, ge=0, description='Смещение страницы'),
    _current_admin: UserEntity = Depends(get_current_admin_user),
    direct_service: DirectService = Depends(Provide[DependencyContainer.direct_service]),
) -> DirectRequestListResponse:
    records, total = await direct_service.list_requests(
        filters=filters, limit=limit, offset=offset,
    )
    return DirectRequestListResponse(
        items=[
            DirectRequestResponse.model_validate(obj=record, from_attributes=True)
            for record in records
        ],
        meta=PaginationMeta(total=total, limit=limit, offset=offset),
    )
