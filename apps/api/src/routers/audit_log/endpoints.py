from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Query

from apps.api.src.container import DependencyContainer
from apps.api.src.routers.audit_log.dependencies import get_audit_log_filters
from apps.api.src.routers.audit_log.schema import AuditLogListResponse, AuditLogResponse
from apps.api.src.routers.billing.dependencies import get_current_admin_user
from apps.api.src.routers.schema import PaginationMeta
from packages.audit_log.src.entities import AuditLogFilters
from packages.audit_log.src.service import AuditLogService
from packages.user.src.entities import UserEntity

admin_router = APIRouter(prefix='/admin/audit-logs', tags=['Audit Log Admin'])


@admin_router.get('/')
@inject
async def list_audit_logs(
    filters: AuditLogFilters = Depends(get_audit_log_filters),
    limit: int = Query(default=100, ge=1, le=500, description='Размер страницы'),
    offset: int = Query(default=0, ge=0, description='Смещение страницы'),
    _current_admin: UserEntity = Depends(get_current_admin_user),
    audit_log_service: AuditLogService = Depends(Provide[DependencyContainer.audit_log_service]),
) -> AuditLogListResponse:
    items, total = await audit_log_service.list_page(filters=filters, limit=limit, offset=offset)
    return AuditLogListResponse(
        items=[AuditLogResponse.model_validate(obj=item, from_attributes=True) for item in items],
        meta=PaginationMeta(total=total, limit=limit, offset=offset),
    )
