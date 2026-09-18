from datetime import timedelta
from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, status

from apps.api.src.container import DependencyContainer
from apps.api.src.routers.auth.dependencies import get_current_user
from apps.api.src.routers.task.schema import CreateTaskRequest, TaskResponse, TaskStatusResponse
from core.exceptions import ObjectNotFoundError
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
