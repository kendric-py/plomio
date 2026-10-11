from datetime import timedelta
from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Query, Response, status

from apps.api.src.container import DependencyContainer
from apps.api.src.routers.automation_admin.dependencies import (
    automation_not_found,
    build_detail_response,
    build_item_response,
    get_admin_automation_filters,
    get_overdue_grace,
)
from apps.api.src.routers.automation_admin.schema import (
    AdminAutomationItemResponse,
    AdminAutomationListResponse,
    AdminAutomationNotificationListResponse,
    AdminAutomationResponse,
    AdminAutomationSummaryResponse,
)
from apps.api.src.routers.billing.dependencies import get_current_admin_user
from apps.api.src.routers.dependencies import get_date_range
from apps.api.src.routers.schema import DateRange, PaginationMeta
from apps.api.src.routers.task_admin.schema import AdminTaskNotificationResponse
from core.exceptions import ObjectNotFoundError
from packages.automation.src.entities import AdminAutomationFilters
from packages.automation.src.service import AutomationService
from packages.notifications.src.service import NotificationService
from packages.task.src.service import TaskService
from packages.user.src.entities import UserEntity

admin_router = APIRouter(prefix='/admin/automations', tags=['Automations Admin'])


@admin_router.get('/summary')
@inject
async def get_automations_summary(
    date_range: DateRange = Depends(get_date_range),
    overdue_grace: timedelta = Depends(get_overdue_grace),
    _current_admin: UserEntity = Depends(get_current_admin_user),
    task_service: TaskService = Depends(Provide[DependencyContainer.task_service]),
    automation_service: AutomationService = Depends(
        Provide[DependencyContainer.automation_service],
    ),
) -> AdminAutomationSummaryResponse:
    task_summary = await task_service.get_summary(
        date_from=date_range.date_from, date_to=date_range.date_to,
    )
    automation_summary = await automation_service.get_admin_summary(
        date_from=date_range.date_from, date_to=date_range.date_to,
        overdue_grace=overdue_grace,
    )
    return AdminAutomationSummaryResponse.model_validate(
        obj={'automations': automation_summary, 'check_tasks': task_summary['automations']},
    )


@admin_router.get('/')
@inject
async def list_automations(
    filters: AdminAutomationFilters = Depends(get_admin_automation_filters),
    limit: int = Query(default=50, ge=1, le=500, description='Размер страницы'),
    offset: int = Query(default=0, ge=0, description='Смещение страницы'),
    _current_admin: UserEntity = Depends(get_current_admin_user),
    automation_service: AutomationService = Depends(
        Provide[DependencyContainer.automation_service],
    ),
) -> AdminAutomationListResponse:
    automations, total = await automation_service.list_automations_admin(
        filters=filters, limit=limit, offset=offset,
    )
    return AdminAutomationListResponse(
        items=[
            build_item_response(automation=automation, grace=filters.overdue_grace)
            for automation in automations
        ],
        meta=PaginationMeta(total=total, limit=limit, offset=offset),
    )


@admin_router.get('/{automation_id}')
@inject
async def get_automation(
    automation_id: UUID,
    overdue_grace: timedelta = Depends(get_overdue_grace),
    _current_admin: UserEntity = Depends(get_current_admin_user),
    automation_service: AutomationService = Depends(
        Provide[DependencyContainer.automation_service],
    ),
) -> AdminAutomationResponse:
    try:
        automation, last_info = await automation_service.get_automation(
            automation_id=automation_id,
        )
    except ObjectNotFoundError as error:
        raise automation_not_found() from error
    return build_detail_response(
        automation=automation, last_info=last_info, grace=overdue_grace,
    )


@admin_router.post('/{automation_id}/pause')
@inject
async def pause_automation(
    automation_id: UUID,
    overdue_grace: timedelta = Depends(get_overdue_grace),
    _current_admin: UserEntity = Depends(get_current_admin_user),
    automation_service: AutomationService = Depends(
        Provide[DependencyContainer.automation_service],
    ),
) -> AdminAutomationItemResponse:
    try:
        automation = await automation_service.pause_automation(automation_id=automation_id)
    except ObjectNotFoundError as error:
        raise automation_not_found() from error
    return build_item_response(automation=automation, grace=overdue_grace)


@admin_router.post('/{automation_id}/resume')
@inject
async def resume_automation(
    automation_id: UUID,
    overdue_grace: timedelta = Depends(get_overdue_grace),
    _current_admin: UserEntity = Depends(get_current_admin_user),
    automation_service: AutomationService = Depends(
        Provide[DependencyContainer.automation_service],
    ),
) -> AdminAutomationItemResponse:
    try:
        automation = await automation_service.resume_automation(automation_id=automation_id)
    except ObjectNotFoundError as error:
        raise automation_not_found() from error
    return build_item_response(automation=automation, grace=overdue_grace)


@admin_router.delete('/{automation_id}', status_code=status.HTTP_204_NO_CONTENT)
@inject
async def delete_automation(
    automation_id: UUID,
    _current_admin: UserEntity = Depends(get_current_admin_user),
    automation_service: AutomationService = Depends(
        Provide[DependencyContainer.automation_service],
    ),
) -> Response:
    try:
        await automation_service.delete_automation(automation_id=automation_id)
    except ObjectNotFoundError as error:
        raise automation_not_found() from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@admin_router.get('/{automation_id}/notifications')
@inject
async def list_automation_notifications(
    automation_id: UUID,
    limit: int = Query(default=20, ge=1, le=200, description='Размер страницы'),
    offset: int = Query(default=0, ge=0, description='Смещение страницы'),
    _current_admin: UserEntity = Depends(get_current_admin_user),
    automation_service: AutomationService = Depends(
        Provide[DependencyContainer.automation_service],
    ),
    notification_service: NotificationService = Depends(
        Provide[DependencyContainer.notification_service],
    ),
) -> AdminAutomationNotificationListResponse:
    try:
        await automation_service.get_automation(automation_id=automation_id)
    except ObjectNotFoundError as error:
        raise automation_not_found() from error
    items, total = await notification_service.list_deliveries_for_automation(
        automation_id=automation_id, limit=limit, offset=offset,
    )
    return AdminAutomationNotificationListResponse(
        items=[
            AdminTaskNotificationResponse.model_validate(obj=item, from_attributes=True)
            for item in items
        ],
        meta=PaginationMeta(total=total, limit=limit, offset=offset),
    )
