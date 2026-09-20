from datetime import timedelta
from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Query, status

from apps.api.src.container import DependencyContainer
from apps.api.src.routers.auth.dependencies import get_current_user
from apps.api.src.routers.task.schema import (
    CreateTaskRequest,
    PaginationMeta,
    ResultItemResponse,
    TaskListItemResponse,
    TaskListResponse,
    TaskResponse,
    TaskResultsResponse,
    TaskStatusResponse,
)
from core.exceptions import ObjectNotFoundError
from packages.result.src.service import ResultService
from packages.task.src.enums import TaskStatus
from packages.task.src.service import TaskService
from packages.user.src.entities import UserEntity

router = APIRouter(prefix='/tasks', tags=['Tasks'])


@router.post('/', status_code=status.HTTP_201_CREATED)
@inject
async def create_task(
    body: CreateTaskRequest,
    current_user: UserEntity = Depends(get_current_user),
    task_service: TaskService = Depends(
        Provide[DependencyContainer.task_service],
    ),
) -> TaskResponse:
    task = await task_service.create_task(
        parse_type=body.parse_type,
        marketplace=body.marketplace,
        inputs=body.inputs,
        priority=body.priority,
        ttl=timedelta(seconds=body.ttl_seconds),
        user_id=current_user.id,
        result_limit=body.result_limit,
    )
    return TaskResponse.model_validate(obj=task, from_attributes=True)


@router.get('/')
@inject
async def list_tasks(
    limit: int = Query(default=100, ge=1, le=500, description='Размер страницы'),
    offset: int = Query(default=0, ge=0, description='Смещение страницы'),
    task_status: TaskStatus | None = Query(
        default=None, alias='status', description='Фильтр по статусу задачи',
    ),
    current_user: UserEntity = Depends(get_current_user),
    task_service: TaskService = Depends(
        Provide[DependencyContainer.task_service],
    ),
) -> TaskListResponse:
    items, total = await task_service.list_tasks(
        user_id=current_user.id, limit=limit, offset=offset, status=task_status,
    )
    return TaskListResponse(
        items=[TaskListItemResponse.model_validate(obj=item) for item in items],
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
) -> TaskStatusResponse:
    try:
        task_status = await task_service.get_task_status(task_id=task_id, user_id=current_user.id)
    except ObjectNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Task not found',
        ) from error
    return TaskStatusResponse.model_validate(
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
