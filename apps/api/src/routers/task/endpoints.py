from datetime import timedelta
from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.concurrency import run_in_threadpool

from apps.api.src.container import DependencyContainer
from apps.api.src.routers.auth.dependencies import get_current_user
from apps.api.src.routers.dependencies import get_date_range
from apps.api.src.routers.schema import DateRange, PaginationMeta
from apps.api.src.routers.task.schema import (
    CreateTaskRequest,
    CreateTaskResponse,
    ResultItemResponse,
    ResumeTaskRequest,
    TaskDetailResponse,
    TaskItemResponse,
    TaskListResponse,
    TaskResultsResponse,
)
from apps.api.src.routers.task.xlsx_export import build_results_xlsx
from core.exceptions import ObjectNotFoundError
from packages.billing.src.exceptions import InsufficientCreditsError
from packages.result.src.service import ResultService
from packages.task.src.enums import TaskStatus
from packages.task.src.exceptions import InvalidTaskTransitionError
from packages.task.src.service import TaskService
from packages.user.src.entities import UserEntity

router = APIRouter(prefix='/tasks', tags=['Tasks'])

EXPORT_PAGE_SIZE = 500
XLSX_MEDIA_TYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


@router.post('/', status_code=status.HTTP_201_CREATED)
@inject
async def create_task(
    body: CreateTaskRequest,
    current_user: UserEntity = Depends(get_current_user),
    task_service: TaskService = Depends(
        Provide[DependencyContainer.task_service],
    ),
) -> CreateTaskResponse:
    try:
        task = await task_service.create_task(
            parse_type=body.parse_type,
            marketplace=body.marketplace,
            inputs=body.inputs,
            priority=body.priority,
            ttl=timedelta(seconds=body.ttl_seconds),
            user_id=current_user.id,
            result_limit=body.result_limit,
        )
    except InsufficientCreditsError as error:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail='Insufficient credits',
        ) from error
    items = await task_service.get_task_items(task_id=task.id)
    return CreateTaskResponse.model_validate(
        obj={
            **task.model_dump(),
            'items': [
                TaskItemResponse.model_validate(obj=item, from_attributes=True) for item in items
            ],
        },
    )


@router.get('/')
@inject
async def list_tasks(
    limit: int = Query(default=100, ge=1, le=500, description='Размер страницы'),
    offset: int = Query(default=0, ge=0, description='Смещение страницы'),
    task_status: TaskStatus | None = Query(
        default=None, alias='status', description='Фильтр по статусу задачи',
    ),
    date_range: DateRange = Depends(get_date_range),
    current_user: UserEntity = Depends(get_current_user),
    task_service: TaskService = Depends(
        Provide[DependencyContainer.task_service],
    ),
) -> TaskListResponse:
    items, total = await task_service.list_tasks(
        user_id=current_user.id,
        limit=limit,
        offset=offset,
        status=task_status,
        date_from=date_range.date_from,
        date_to=date_range.date_to,
    )
    return TaskListResponse(
        items=[TaskDetailResponse.model_validate(obj=item) for item in items],
        meta=PaginationMeta(total=total, limit=limit, offset=offset),
    )


@router.get('/{task_id}')
@inject
async def get_task_status(
    task_id: UUID,
    current_user: UserEntity = Depends(get_current_user),
    task_service: TaskService = Depends(
        Provide[DependencyContainer.task_service],
    ),
) -> TaskDetailResponse:
    try:
        task_status = await task_service.get_task_status(task_id=task_id, user_id=current_user.id)
    except ObjectNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Task not found',
        ) from error
    return TaskDetailResponse.model_validate(
        obj={**task_status['task'].model_dump(), **task_status['progress']},
    )


@router.get('/{task_id}/results')
@inject
async def get_task_results(
    task_id: UUID,
    limit: int = Query(default=100, ge=1, le=500, description='Размер страницы'),
    offset: int = Query(default=0, ge=0, description='Смещение страницы'),
    current_user: UserEntity = Depends(get_current_user),
    task_service: TaskService = Depends(
        Provide[DependencyContainer.task_service],
    ),
    result_service: ResultService = Depends(
        Provide[DependencyContainer.result_service],
    ),
) -> TaskResultsResponse:
    try:
        await task_service.ensure_task_owner(task_id=task_id, user_id=current_user.id)
    except ObjectNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Task not found',
        ) from error

    items, total = await result_service.get_results_for_task(
        task_id=task_id, limit=limit, offset=offset,
    )
    return TaskResultsResponse(
        items=[
            ResultItemResponse.model_validate(obj=item, from_attributes=True) for item in items
        ],
        meta=PaginationMeta(total=total, limit=limit, offset=offset),
    )


@router.get('/{task_id}/results/export')
@inject
async def export_task_results(
    task_id: UUID,
    current_user: UserEntity = Depends(get_current_user),
    task_service: TaskService = Depends(
        Provide[DependencyContainer.task_service],
    ),
    result_service: ResultService = Depends(
        Provide[DependencyContainer.result_service],
    ),
) -> Response:
    try:
        await task_service.ensure_task_owner(task_id=task_id, user_id=current_user.id)
    except ObjectNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Task not found',
        ) from error

    results = []
    while True:
        page, total = await result_service.get_results_for_task(
            task_id=task_id, limit=EXPORT_PAGE_SIZE, offset=len(results),
        )
        results.extend(page)
        if not page or len(results) >= total:
            break
    content = await run_in_threadpool(build_results_xlsx, results)
    return Response(
        content=content,
        media_type=XLSX_MEDIA_TYPE,
        headers={'Content-Disposition': f'attachment; filename="task_{task_id}_results.xlsx"'},
    )


@router.post('/{task_id}/cancel')
@inject
async def cancel_task(
    task_id: UUID,
    current_user: UserEntity = Depends(get_current_user),
    task_service: TaskService = Depends(
        Provide[DependencyContainer.task_service],
    ),
) -> TaskDetailResponse:
    try:
        task = await task_service.cancel_task(task_id=task_id, user_id=current_user.id)
    except ObjectNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Task not found',
        ) from error
    except InvalidTaskTransitionError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Task cannot be cancelled in its current status',
        ) from error
    progress = await task_service.get_progress(task_id=task_id)
    return TaskDetailResponse.model_validate(obj={**task.model_dump(), **progress})


@router.post('/{task_id}/pause')
@inject
async def pause_task(
    task_id: UUID,
    current_user: UserEntity = Depends(get_current_user),
    task_service: TaskService = Depends(
        Provide[DependencyContainer.task_service],
    ),
) -> TaskDetailResponse:
    try:
        task = await task_service.pause_task(task_id=task_id, user_id=current_user.id)
    except ObjectNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Task not found',
        ) from error
    except InvalidTaskTransitionError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Task cannot be paused in its current status',
        ) from error
    progress = await task_service.get_progress(task_id=task_id)
    return TaskDetailResponse.model_validate(obj={**task.model_dump(), **progress})


@router.post('/{task_id}/resume')
@inject
async def resume_task(
    task_id: UUID,
    body: ResumeTaskRequest,
    current_user: UserEntity = Depends(get_current_user),
    task_service: TaskService = Depends(
        Provide[DependencyContainer.task_service],
    ),
) -> TaskDetailResponse:
    try:
        task = await task_service.resume_task(
            task_id=task_id,
            user_id=current_user.id,
            ttl=timedelta(seconds=body.ttl_seconds),
        )
    except ObjectNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Task not found',
        ) from error
    except InsufficientCreditsError as error:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail='Insufficient credits',
        ) from error
    except InvalidTaskTransitionError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Task is not paused',
        ) from error
    progress = await task_service.get_progress(task_id=task_id)
    return TaskDetailResponse.model_validate(obj={**task.model_dump(), **progress})


@router.delete('/{task_id}', status_code=status.HTTP_204_NO_CONTENT)
@inject
async def delete_task(
    task_id: UUID,
    current_user: UserEntity = Depends(get_current_user),
    task_service: TaskService = Depends(
        Provide[DependencyContainer.task_service],
    ),
) -> None:
    try:
        await task_service.delete_task(task_id=task_id, user_id=current_user.id)
    except ObjectNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Task not found',
        ) from error
