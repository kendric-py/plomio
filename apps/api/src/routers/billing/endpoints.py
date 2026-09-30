from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Query, status

from apps.api.src.container import DependencyContainer
from apps.api.src.routers.auth.dependencies import get_current_user
from apps.api.src.routers.billing.dependencies import get_current_admin_user
from apps.api.src.routers.billing.schema import (
    BalanceResponse,
    BillingActionListResponse,
    BillingActionResponse,
    CreatePricingRuleRequest,
    CreditTransactionGroupListResponse,
    CreditTransactionGroupResponse,
    CreditTransactionResponse,
    GrantCreditsRequest,
    PricingMultiplierRuleListResponse,
    PricingMultiplierRuleResponse,
    UpdateActionCostRequest,
)
from apps.api.src.routers.schema import PaginationMeta
from core.exceptions import ObjectNotFoundError
from packages.billing.src.exceptions import OverlappingPricingRuleError
from packages.billing.src.service import BillingService
from packages.user.src.entities import UserEntity

router = APIRouter(prefix='/billing', tags=['Billing'])
admin_router = APIRouter(prefix='/admin/billing', tags=['Billing Admin'])


@router.get('/balance')
@inject
async def get_balance(
    current_user: UserEntity = Depends(get_current_user),
    billing_service: BillingService = Depends(Provide[DependencyContainer.billing_service]),
) -> BalanceResponse:
    balance = await billing_service.get_balance(user_id=current_user.id)
    return BalanceResponse(balance=balance)


@router.get('/transactions/by-reference')
@inject
async def list_transactions_by_reference(
    limit: int = Query(default=100, ge=1, le=500, description='Размер страницы'),
    offset: int = Query(default=0, ge=0, description='Смещение страницы'),
    current_user: UserEntity = Depends(get_current_user),
    billing_service: BillingService = Depends(Provide[DependencyContainer.billing_service]),
) -> CreditTransactionGroupListResponse:
    items, total = await billing_service.list_transactions_grouped_by_reference(
        user_id=current_user.id, limit=limit, offset=offset,
    )
    return CreditTransactionGroupListResponse(
        items=[
            CreditTransactionGroupResponse.model_validate(obj=item, from_attributes=True)
            for item in items
        ],
        meta=PaginationMeta(total=total, limit=limit, offset=offset),
    )


@admin_router.get('/actions')
@inject
async def list_actions(
    _current_admin: UserEntity = Depends(get_current_admin_user),
    billing_service: BillingService = Depends(Provide[DependencyContainer.billing_service]),
) -> BillingActionListResponse:
    actions = await billing_service.list_actions()
    return BillingActionListResponse(
        items=[
            BillingActionResponse.model_validate(obj=action, from_attributes=True)
            for action in actions
        ],
    )


@admin_router.patch('/actions/{action_code}')
@inject
async def update_action_cost(
    action_code: str,
    body: UpdateActionCostRequest,
    _current_admin: UserEntity = Depends(get_current_admin_user),
    billing_service: BillingService = Depends(Provide[DependencyContainer.billing_service]),
) -> BillingActionResponse:
    try:
        action = await billing_service.update_action_cost(
            action_code=action_code, base_cost=body.base_cost,
        )
    except ObjectNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Billing action not found',
        ) from error
    return BillingActionResponse.model_validate(obj=action, from_attributes=True)


@admin_router.get('/pricing-rules')
@inject
async def list_pricing_rules(
    dimension_code: str | None = Query(default=None, description='Фильтр по коду измерения'),
    _current_admin: UserEntity = Depends(get_current_admin_user),
    billing_service: BillingService = Depends(Provide[DependencyContainer.billing_service]),
) -> PricingMultiplierRuleListResponse:
    rules = await billing_service.list_pricing_rules(dimension_code=dimension_code)
    return PricingMultiplierRuleListResponse(
        items=[
            PricingMultiplierRuleResponse.model_validate(obj=rule, from_attributes=True)
            for rule in rules
        ],
    )


@admin_router.post('/pricing-rules', status_code=status.HTTP_201_CREATED)
@inject
async def create_pricing_rule(
    body: CreatePricingRuleRequest,
    _current_admin: UserEntity = Depends(get_current_admin_user),
    billing_service: BillingService = Depends(Provide[DependencyContainer.billing_service]),
) -> PricingMultiplierRuleResponse:
    try:
        rule = await billing_service.create_pricing_rule(
            dimension_code=body.dimension_code,
            value_min=body.value_min,
            value_max=body.value_max,
            multiplier=body.multiplier,
        )
    except OverlappingPricingRuleError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Pricing rule range overlaps an existing rule for this dimension_code',
        ) from error
    return PricingMultiplierRuleResponse.model_validate(obj=rule, from_attributes=True)


@admin_router.delete('/pricing-rules/{rule_id}', status_code=status.HTTP_204_NO_CONTENT)
@inject
async def delete_pricing_rule(
    rule_id: int,
    _current_admin: UserEntity = Depends(get_current_admin_user),
    billing_service: BillingService = Depends(Provide[DependencyContainer.billing_service]),
) -> None:
    try:
        await billing_service.delete_pricing_rule(rule_id=rule_id)
    except ObjectNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Pricing rule not found',
        ) from error


@admin_router.post('/users/{user_id}/grant', status_code=status.HTTP_201_CREATED)
@inject
async def grant_credits(
    user_id: int,
    body: GrantCreditsRequest,
    current_admin: UserEntity = Depends(get_current_admin_user),
    billing_service: BillingService = Depends(Provide[DependencyContainer.billing_service]),
) -> CreditTransactionResponse:
    transaction = await billing_service.grant(
        user_id=user_id, amount=body.amount, admin_id=current_admin.id, comment=body.comment,
    )
    return CreditTransactionResponse.model_validate(obj=transaction, from_attributes=True)
