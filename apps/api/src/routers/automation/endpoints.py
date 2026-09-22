from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Query, status

from apps.api.src.config import config
from apps.api.src.container import DependencyContainer
from apps.api.src.routers.auth.dependencies import get_current_user
from apps.api.src.routers.automation.schema import (
    AutomationHistoryListResponse,
    AutomationHistoryResponse,
    AutomationListResponse,
    AutomationResponse,
    CreateAutomationRequest,
    PaginationMeta,
    UpdateBaselineRequest,
)
from core.exceptions import ObjectNotFoundError
from packages.automation.src.exceptions import DuplicateAutomationError, InvalidCheckFrequencyError
from packages.automation.src.service import AutomationService
from packages.user.src.entities import UserEntity

router = APIRouter(prefix='/automations', tags=['Automations'])


@router.post('/', status_code=status.HTTP_201_CREATED)
@inject
async def create_automation(
    body: CreateAutomationRequest,
    current_user: UserEntity = Depends(get_current_user),
    automation_service: AutomationService = Depends(
        Provide[DependencyContainer.automation_service],
    ),
) -> AutomationResponse:
    try:
        automation = await automation_service.create_automation(
            user_id=current_user.id,
            marketplace=body.marketplace,
            input_value=body.input_value,
            price_drop_threshold_percent=body.price_drop_threshold_percent,
            check_frequency_minutes=body.check_frequency_minutes,
            history_retention_days=body.history_retention_days,
            min_check_frequency_minutes=config.AUTOMATION.MIN_CHECK_FREQUENCY_MINUTES,
        )
    except InvalidCheckFrequencyError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                'check_frequency_minutes must be at least '
                f'{config.AUTOMATION.MIN_CHECK_FREQUENCY_MINUTES}'
            ),
        ) from error
    except DuplicateAutomationError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='An automation for this product already exists',
        ) from error
    return AutomationResponse.model_validate(obj=automation, from_attributes=True)


@router.get('/')
@inject
async def list_automations(
    limit: int = Query(default=100, ge=1, le=500, description='Размер страницы'),
    offset: int = Query(default=0, ge=0, description='Смещение страницы'),
    current_user: UserEntity = Depends(get_current_user),
    automation_service: AutomationService = Depends(
        Provide[DependencyContainer.automation_service],
    ),
) -> AutomationListResponse:
    items, total = await automation_service.list_automations(
        user_id=current_user.id, limit=limit, offset=offset,
    )
    return AutomationListResponse(
        items=[
            AutomationResponse.model_validate(obj=item, from_attributes=True) for item in items
        ],
        meta=PaginationMeta(total=total, limit=limit, offset=offset),
    )


@router.get('/{automation_id}')
@inject
async def get_automation(
    automation_id: UUID,
    current_user: UserEntity = Depends(get_current_user),
    automation_service: AutomationService = Depends(
        Provide[DependencyContainer.automation_service],
    ),
) -> AutomationResponse:
    try:
        automation = await automation_service.get_automation(
            automation_id=automation_id, user_id=current_user.id,
        )
    except ObjectNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Automation not found',
        ) from error
    return AutomationResponse.model_validate(obj=automation, from_attributes=True)


@router.patch('/{automation_id}/baseline')
@inject
async def update_automation_baseline(
    automation_id: UUID,
    body: UpdateBaselineRequest,
    current_user: UserEntity = Depends(get_current_user),
    automation_service: AutomationService = Depends(
        Provide[DependencyContainer.automation_service],
    ),
) -> AutomationResponse:
    try:
        automation = await automation_service.update_baseline(
            automation_id=automation_id,
            user_id=current_user.id,
            price_kopecks=body.price_kopecks,
            discounted_price_kopecks=body.discounted_price_kopecks,
            original_price_kopecks=body.original_price_kopecks,
        )
    except ObjectNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Automation not found',
        ) from error
    return AutomationResponse.model_validate(obj=automation, from_attributes=True)


@router.post('/{automation_id}/pause')
@inject
async def pause_automation(
    automation_id: UUID,
    current_user: UserEntity = Depends(get_current_user),
    automation_service: AutomationService = Depends(
        Provide[DependencyContainer.automation_service],
    ),
) -> AutomationResponse:
    try:
        automation = await automation_service.pause_automation(
            automation_id=automation_id, user_id=current_user.id,
        )
    except ObjectNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Automation not found',
        ) from error
    return AutomationResponse.model_validate(obj=automation, from_attributes=True)


@router.post('/{automation_id}/resume')
@inject
async def resume_automation(
    automation_id: UUID,
    current_user: UserEntity = Depends(get_current_user),
    automation_service: AutomationService = Depends(
        Provide[DependencyContainer.automation_service],
    ),
) -> AutomationResponse:
    try:
        automation = await automation_service.resume_automation(
            automation_id=automation_id, user_id=current_user.id,
        )
    except ObjectNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Automation not found',
        ) from error
    return AutomationResponse.model_validate(obj=automation, from_attributes=True)


@router.delete('/{automation_id}', status_code=status.HTTP_204_NO_CONTENT)
@inject
async def delete_automation(
    automation_id: UUID,
    current_user: UserEntity = Depends(get_current_user),
    automation_service: AutomationService = Depends(
        Provide[DependencyContainer.automation_service],
    ),
) -> None:
    try:
        await automation_service.delete_automation(
            automation_id=automation_id, user_id=current_user.id,
        )
    except ObjectNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Automation not found',
        ) from error


@router.get('/{automation_id}/history')
@inject
async def get_automation_history(
    automation_id: UUID,
    limit: int = Query(default=100, ge=1, le=500, description='Размер страницы'),
    offset: int = Query(default=0, ge=0, description='Смещение страницы'),
    current_user: UserEntity = Depends(get_current_user),
    automation_service: AutomationService = Depends(
        Provide[DependencyContainer.automation_service],
    ),
) -> AutomationHistoryListResponse:
    try:
        items, total = await automation_service.list_history(
            automation_id=automation_id, user_id=current_user.id, limit=limit, offset=offset,
        )
    except ObjectNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Automation not found',
        ) from error
    return AutomationHistoryListResponse(
        items=[
            AutomationHistoryResponse.model_validate(obj=item, from_attributes=True)
            for item in items
        ],
        meta=PaginationMeta(total=total, limit=limit, offset=offset),
    )
