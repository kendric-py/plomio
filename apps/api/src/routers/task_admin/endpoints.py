from datetime import timedelta
from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Query, status

from apps.api.src.container import DependencyContainer
from apps.api.src.routers.billing.dependencies import get_current_admin_user
from apps.api.src.routers.dependencies import get_date_range
from apps.api.src.routers.schema import DateRange, PaginationMeta
from apps.api.src.routers.task.schema import (
    ResultItemResponse,
    ResumeTaskRequest,
    TaskDetailResponse,
    TaskResultsResponse,
)
from apps.api.src.routers.task_admin.dependencies import get_admin_task_filters
from apps.api.src.routers.task_admin.schema import (
    AdminTaskDetailResponse,
    AdminTaskItemResponse,
    AdminTaskListItemResponse,
    AdminTaskListResponse,
    AdminTaskNotificationResponse,
    AdminTaskSummaryResponse,
    RestartTaskRequest,
)
from core.exceptions import ObjectNotFoundError
from packages.billing.src.exceptions import InsufficientCreditsError
from packages.notifications.src.service import NotificationService
from packages.result.src.service import ResultService
from packages.task.src.entities import AdminTaskFilters, TaskEntity
from packages.task.src.exceptions import InvalidTaskTransitionError, TaskItemNotExcludableError
from packages.task.src.service import TaskService
from packages.user.src.entities import UserEntity

admin_router = APIRouter(prefix='/admin/tasks', tags=['Tasks Admin'])


def _task_not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task not found')


def _insufficient_credits(error: InsufficientCreditsError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=error.detail)


async def _task_detail(task_service: TaskService, task: TaskEntity) -> TaskDetailResponse:
    progress = await task_service.get_progress(task_id=task.id)
    return TaskDetailResponse.model_validate(obj={**task.model_dump(), **progress})


@admin_router.get('/summary')
@inject
async def get_tasks_summary(
    date_range: DateRange = Depends(get_date_range),
    _current_admin: UserEntity = Depends(get_current_admin_user),
    task_service: TaskService = Depends(Provide[DependencyContainer.task_service]),
) -> AdminTaskSummaryResponse:
    task_summary = await task_service.get_summary(
        date_from=date_range.date_from, date_to=date_range.date_to,
    )
    return AdminTaskSummaryResponse.model_validate(obj={'tasks': task_summary['tasks']})


@admin_router.get('/')
@inject
async def list_tasks(
    filters: AdminTaskFilters = Depends(get_admin_task_filters),
    limit: int = Query(default=50, ge=1, le=500, description='Размер страницы'),
    offset: int = Query(default=0, ge=0, description='Смещение страницы'),
    _current_admin: UserEntity = Depends(get_current_admin_user),
    task_service: TaskService = Depends(Provide[DependencyContainer.task_service]),
) -> AdminTaskListResponse:
    items, total = await task_service.list_tasks_admin(
        filters=filters, limit=limit, offset=offset,
    )
    return AdminTaskListResponse(
        items=[
            AdminTaskListItemResponse.model_validate(
                obj={
                    **item,
                    'failed_items': [
                        failed_item.model_dump() for failed_item in item['failed_items']
                    ],
                },
            )
            for item in items
        ],
        meta=PaginationMeta(total=total, limit=limit, offset=offset),
    )


@admin_router.get('/{task_id}')
@inject
async def get_task(
    task_id: UUID,
    _current_admin: UserEntity = Depends(get_current_admin_user),
    task_service: TaskService = Depends(Provide[DependencyContainer.task_service]),
    notification_service: NotificationService = Depends(
        Provide[DependencyContainer.notification_service],
    ),
) -> AdminTaskDetailResponse:
    try:
        detail = await task_service.get_task_admin(task_id=task_id)
    except ObjectNotFoundError as error:
        raise _task_not_found() from error
    deliveries = await notification_service.list_deliveries_for_task(
        task_id=task_id,
        automation_id=detail['task'].automation_id,
        finished_at=detail['task'].finished_at,
    )
    return AdminTaskDetailResponse.model_validate(
        obj={
            **detail['task'].model_dump(),
            **detail['progress'],
            'items': [
                AdminTaskItemResponse.model_validate(obj=item, from_attributes=True)
                for item in detail['items']
            ],
            'notifications': [
                AdminTaskNotificationResponse.model_validate(obj=delivery, from_attributes=True)
                for delivery in deliveries
            ],
        },
    )


@admin_router.get('/{task_id}/results')
@inject
async def get_task_results(
    task_id: UUID,
    limit: int = Query(default=100, ge=1, le=500, description='Размер страницы'),
    offset: int = Query(default=0, ge=0, description='Смещение страницы'),
    _current_admin: UserEntity = Depends(get_current_admin_user),
    task_service: TaskService = Depends(Provide[DependencyContainer.task_service]),
    result_service: ResultService = Depends(Provide[DependencyContainer.result_service]),
) -> TaskResultsResponse:
    try:
        await task_service.get_task_by_id(task_id=task_id)
    except ObjectNotFoundError as error:
        raise _task_not_found() from error
    items, total = await result_service.get_results_for_task(
        task_id=task_id, limit=limit, offset=offset,
    )
    return TaskResultsResponse(
        items=[
            ResultItemResponse.model_validate(obj=item, from_attributes=True) for item in items
        ],
        meta=PaginationMeta(total=total, limit=limit, offset=offset),
    )


@admin_router.post('/{task_id}/cancel')
@inject
async def cancel_task(
    task_id: UUID,
    _current_admin: UserEntity = Depends(get_current_admin_user),
    task_service: TaskService = Depends(Provide[DependencyContainer.task_service]),
) -> TaskDetailResponse:
    try:
        task = await task_service.cancel_task(task_id=task_id)
    except ObjectNotFoundError as error:
        raise _task_not_found() from error
    except InvalidTaskTransitionError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Task cannot be cancelled in its current status',
        ) from error
    return await _task_detail(task_service, task)


@admin_router.post('/{task_id}/pause')
@inject
async def pause_task(
    task_id: UUID,
    _current_admin: UserEntity = Depends(get_current_admin_user),
    task_service: TaskService = Depends(Provide[DependencyContainer.task_service]),
) -> TaskDetailResponse:
    try:
        task = await task_service.pause_task(task_id=task_id)
    except ObjectNotFoundError as error:
        raise _task_not_found() from error
    except InvalidTaskTransitionError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Task cannot be paused in its current status',
        ) from error
    return await _task_detail(task_service, task)


@admin_router.post('/{task_id}/resume')
@inject
async def resume_task(
    task_id: UUID,
    body: ResumeTaskRequest,
    _current_admin: UserEntity = Depends(get_current_admin_user),
    task_service: TaskService = Depends(Provide[DependencyContainer.task_service]),
) -> TaskDetailResponse:
    try:
        task = await task_service.resume_task(
            task_id=task_id, ttl=timedelta(seconds=body.ttl_seconds),
        )
    except ObjectNotFoundError as error:
        raise _task_not_found() from error
    except InsufficientCreditsError as error:
        raise _insufficient_credits(error) from error
    except InvalidTaskTransitionError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail='Task is not paused',
        ) from error
    return await _task_detail(task_service, task)


@admin_router.post('/{task_id}/restart')
@inject
async def restart_task(
    task_id: UUID,
    body: RestartTaskRequest,
    _current_admin: UserEntity = Depends(get_current_admin_user),
    task_service: TaskService = Depends(Provide[DependencyContainer.task_service]),
) -> TaskDetailResponse:
    try:
        task = await task_service.restart_task(
            task_id=task_id, ttl=timedelta(seconds=body.ttl_seconds),
        )
    except ObjectNotFoundError as error:
        raise _task_not_found() from error
    except InsufficientCreditsError as error:
        raise _insufficient_credits(error) from error
    except InvalidTaskTransitionError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Only FAILED or EXPIRED tasks can be restarted',
        ) from error
    return await _task_detail(task_service, task)


@admin_router.post('/{task_id}/items/{item_id}/exclude')
@inject
async def exclude_task_item(
    task_id: UUID,
    item_id: UUID,
    _current_admin: UserEntity = Depends(get_current_admin_user),
    task_service: TaskService = Depends(Provide[DependencyContainer.task_service]),
) -> TaskDetailResponse:
    try:
        task = await task_service.exclude_task_item(task_id=task_id, item_id=item_id)
    except ObjectNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Task item not found',
        ) from error
    except TaskItemNotExcludableError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Only FAILED task items can be excluded',
        ) from error
    except InsufficientCreditsError as error:
        raise _insufficient_credits(error) from error
    return await _task_detail(task_service, task)
