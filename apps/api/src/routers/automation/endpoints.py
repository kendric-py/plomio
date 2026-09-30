from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Query, status

from apps.api.src.config import config
from apps.api.src.container import DependencyContainer
from apps.api.src.routers.auth.dependencies import get_current_user
from apps.api.src.routers.automation.schema import (
    AutomationDetailResponse,
    AutomationHistoryListResponse,
    AutomationHistoryResponse,
    AutomationListResponse,
    AutomationRecentCheckResponse,
    AutomationResponse,
    AutomationWithHistoryListResponse,
    AutomationWithHistoryResponse,
    CreateAutomationRequest,
    UpdateBaselineRequest,
)
from apps.api.src.routers.dependencies import get_date_range
from apps.api.src.routers.schema import DateRange, PaginationMeta
from core.exceptions import ObjectNotFoundError
from packages.automation.src.exceptions import DuplicateAutomationError, InvalidCheckFrequencyError
from packages.automation.src.service import AutomationService
from packages.billing.src.exceptions import InsufficientCreditsError
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
    except InsufficientCreditsError as error:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail='Insufficient credits',
        ) from error
    return AutomationResponse.model_validate(obj=automation, from_attributes=True)


@router.get('/')
@inject
async def list_automations(
    limit: int = Query(default=100, ge=1, le=500, description='Размер страницы'),
    offset: int = Query(default=0, ge=0, description='Смещение страницы'),
    date_range: DateRange = Depends(get_date_range),
    current_user: UserEntity = Depends(get_current_user),
    automation_service: AutomationService = Depends(
        Provide[DependencyContainer.automation_service],
    ),
) -> AutomationListResponse:
    items, total = await automation_service.list_automations(
        user_id=current_user.id,
        limit=limit,
        offset=offset,
        date_from=date_range.date_from,
        date_to=date_range.date_to,
    )
    return AutomationListResponse(
        items=[
            AutomationResponse.model_validate(obj=item, from_attributes=True) for item in items
        ],
        meta=PaginationMeta(total=total, limit=limit, offset=offset),
    )


@router.get('/with-history')
@inject
async def list_automations_with_history(
    limit: int = Query(default=100, ge=1, le=500, description='Размер страницы'),
    offset: int = Query(default=0, ge=0, description='Смещение страницы'),
    date_range: DateRange = Depends(get_date_range),
    current_user: UserEntity = Depends(get_current_user),
    automation_service: AutomationService = Depends(
        Provide[DependencyContainer.automation_service],
    ),
) -> AutomationWithHistoryListResponse:
    items, total = await automation_service.list_automations_with_recent_checks(
        user_id=current_user.id,
        limit=limit,
        offset=offset,
        date_from=date_range.date_from,
        date_to=date_range.date_to,
    )
    return AutomationWithHistoryListResponse(
        items=[
            AutomationWithHistoryResponse(
                **AutomationResponse.model_validate(
                    obj=automation, from_attributes=True,
                ).model_dump(),
                recent_checks=[
                    AutomationRecentCheckResponse.model_validate(obj=check, from_attributes=True)
                    for check in recent_checks
                ],
            )
            for automation, recent_checks in items
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
) -> AutomationDetailResponse:
    try:
        automation, last_info = await automation_service.get_automation(
            automation_id=automation_id, user_id=current_user.id,
        )
    except ObjectNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Automation not found',
        ) from error
    return AutomationDetailResponse(
        **AutomationResponse.model_validate(obj=automation, from_attributes=True).model_dump(),
        last_info=last_info,
    )


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
