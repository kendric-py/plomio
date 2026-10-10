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
    BulkAutomationErrorCode,
    BulkAutomationResult,
    BulkCreateAutomationsRequest,
    BulkCreateAutomationsResponse,
    CreateAutomationRequest,
    PriceChangeFrequencyPointResponse,
    PriceChangeFrequencyResponse,
    PriceDynamicsResponse,
    PricePointResponse,
    UpdateBaselineRequest,
)
from apps.api.src.routers.automation.dependencies import (
    get_automation_filters,
    get_chart_period,
)
from apps.api.src.routers.schema import DateRange, PaginationMeta
from core.exceptions import ObjectNotFoundError
from packages.automation.src.entities import AutomationCreateData, AutomationListFilters
from packages.automation.src.exceptions import DuplicateAutomationError, InvalidCheckFrequencyError
from packages.automation.src.service import AutomationService
from packages.billing.src.exceptions import InsufficientCreditsError, SpendingLimitExceededError
from packages.user.src.entities import UserEntity

router = APIRouter(prefix='/automations', tags=['Automations'])

BULK_ERROR_CODES = {
    InvalidCheckFrequencyError: BulkAutomationErrorCode.INVALID_CHECK_FREQUENCY,
    DuplicateAutomationError: BulkAutomationErrorCode.DUPLICATE,
    InsufficientCreditsError: BulkAutomationErrorCode.INSUFFICIENT_CREDITS,
    SpendingLimitExceededError: BulkAutomationErrorCode.SPENDING_LIMIT,
}


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
            detail=error.detail,
        ) from error
    return AutomationResponse.model_validate(obj=automation, from_attributes=True)


@router.post('/bulk', status_code=status.HTTP_200_OK)
@inject
async def bulk_create_automations(
    body: BulkCreateAutomationsRequest,
    current_user: UserEntity = Depends(get_current_user),
    automation_service: AutomationService = Depends(
        Provide[DependencyContainer.automation_service],
    ),
) -> BulkCreateAutomationsResponse:
    """Пакет создаётся одним сервисным вызовом (один запрос дублей и один INSERT); отказ элемента
    не откатывает остальные, причины отказов — в `results[i].error`."""
    outcomes = await automation_service.bulk_create_automations(
        user_id=current_user.id,
        items=[
            AutomationCreateData.model_validate(obj=item.model_dump()) for item in body.items
        ],
        min_check_frequency_minutes=config.AUTOMATION.MIN_CHECK_FREQUENCY_MINUTES,
    )
    results = [
        BulkAutomationResult(
            index=index,
            automation=(
                AutomationResponse.model_validate(obj=outcome.automation, from_attributes=True)
                if outcome.automation is not None else None
            ),
            error=BULK_ERROR_CODES[outcome.error] if outcome.error is not None else None,
        )
        for index, outcome in enumerate(outcomes)
    ]
    created = sum(result.automation is not None for result in results)
    return BulkCreateAutomationsResponse(
        results=results, created=created, failed=len(results) - created,
    )


@router.get('/')
@inject
async def list_automations(
    limit: int = Query(default=100, ge=1, le=500, description='Размер страницы'),
    offset: int = Query(default=0, ge=0, description='Смещение страницы'),
    filters: AutomationListFilters = Depends(get_automation_filters),
    current_user: UserEntity = Depends(get_current_user),
    automation_service: AutomationService = Depends(
        Provide[DependencyContainer.automation_service],
    ),
) -> AutomationListResponse:
    items, total = await automation_service.list_automations(
        user_id=current_user.id, limit=limit, offset=offset, filters=filters,
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
    filters: AutomationListFilters = Depends(get_automation_filters),
    current_user: UserEntity = Depends(get_current_user),
    automation_service: AutomationService = Depends(
        Provide[DependencyContainer.automation_service],
    ),
) -> AutomationWithHistoryListResponse:
    items, total = await automation_service.list_automations_with_recent_checks(
        user_id=current_user.id, limit=limit, offset=offset, filters=filters,
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


@router.get('/{automation_id}/charts/price-dynamics')
@inject
async def get_price_dynamics(
    automation_id: UUID,
    period: DateRange = Depends(get_chart_period),
    current_user: UserEntity = Depends(get_current_user),
    automation_service: AutomationService = Depends(
        Provide[DependencyContainer.automation_service],
    ),
) -> PriceDynamicsResponse:
    try:
        step_seconds, points = await automation_service.get_price_dynamics(
            automation_id=automation_id,
            user_id=current_user.id,
            since=period.date_from,
            until=period.date_to,
        )
    except ObjectNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Automation not found',
        ) from error
    return PriceDynamicsResponse(
        date_from=period.date_from,
        date_to=period.date_to,
        step_seconds=step_seconds,
        items=[
            PricePointResponse.model_validate(obj=point, from_attributes=True) for point in points
        ],
    )


@router.get('/{automation_id}/charts/price-change-frequency')
@inject
async def get_price_change_frequency(
    automation_id: UUID,
    period: DateRange = Depends(get_chart_period),
    current_user: UserEntity = Depends(get_current_user),
    automation_service: AutomationService = Depends(
        Provide[DependencyContainer.automation_service],
    ),
) -> PriceChangeFrequencyResponse:
    try:
        step_seconds, points = await automation_service.get_price_change_frequency(
            automation_id=automation_id,
            user_id=current_user.id,
            since=period.date_from,
            until=period.date_to,
        )
    except ObjectNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Automation not found',
        ) from error
    return PriceChangeFrequencyResponse(
        date_from=period.date_from,
        date_to=period.date_to,
        step_seconds=step_seconds,
        items=[
            PriceChangeFrequencyPointResponse.model_validate(obj=point, from_attributes=True)
            for point in points
        ],
    )


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
