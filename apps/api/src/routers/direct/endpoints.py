import logging

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Path, Query
from pydantic import ValidationError

from apps.api.src.container import DependencyContainer
from apps.api.src.routers.auth.dependencies import get_current_user
from apps.api.src.routers.direct.dependencies import (
    build_request,
    charge_direct_request,
    decode_cursor,
    dispatch_request,
    encode_next_page_key,
    parse_reply_items,
    require_positive_balance,
)
from apps.api.src.routers.direct.errors import (
    invalid_category_error,
    invalid_seller_error,
    invalid_search_query_error,
    unavailable_error,
)
from apps.api.src.routers.direct.schema import (
    DirectCategoryResponse,
    DirectProductResponse,
    DirectReviewsResponse,
    DirectSearchResponse,
    DirectSellerResponse,
)
from core.enums import Marketplace
from packages.billing.src.service import BillingService
from packages.direct.src.enums import DirectRequestType
from packages.direct.src.redis_bus import DirectBus
from packages.result.src.entities import ProductPagePayload, ProductPayload, ReviewPayload
from packages.user.src.entities import UserEntity

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix='/marketplace', tags=['Marketplace'], dependencies=[Depends(require_positive_balance)],
)


@router.get('/{marketplace}/product/{article}')
@inject
async def get_product(
    marketplace: Marketplace,
    article: str = Path(min_length=1, max_length=64, description='Артикул товара'),
    bus: DirectBus = Depends(Provide[DependencyContainer.direct_bus]),
    billing_service: BillingService = Depends(Provide[DependencyContainer.billing_service]),
    current_user: UserEntity = Depends(get_current_user),
) -> DirectProductResponse:
    request = build_request(DirectRequestType.PRODUCT_PAGE, marketplace, article, None)
    reply = await dispatch_request(bus, request)
    try:
        product = ProductPagePayload.model_validate(reply.payload)
    except ValidationError as error:
        logger.exception('[direct_api_bad_reply] request_id=%s', reply.request_id)
        raise unavailable_error() from error
    await charge_direct_request(billing_service, current_user.id, request, quantity=1)
    return DirectProductResponse(request_id=reply.request_id, product=product)


@router.get('/{marketplace}/product/{article}/reviews')
@inject
async def get_product_reviews(
    marketplace: Marketplace,
    article: str = Path(min_length=1, max_length=64, description='Артикул товара'),
    page_key: str | None = Query(default=None, description='Ключ страницы из предыдущего ответа'),
    bus: DirectBus = Depends(Provide[DependencyContainer.direct_bus]),
    billing_service: BillingService = Depends(Provide[DependencyContainer.billing_service]),
    current_user: UserEntity = Depends(get_current_user),
) -> DirectReviewsResponse:
    cursor = decode_cursor(page_key, marketplace, article)
    request = build_request(DirectRequestType.REVIEWS, marketplace, article, cursor)
    reply = await dispatch_request(bus, request)
    items = parse_reply_items(reply, ReviewPayload)
    await charge_direct_request(billing_service, current_user.id, request, quantity=len(items))
    return DirectReviewsResponse(
        request_id=reply.request_id,
        items=items,
        next_page_key=encode_next_page_key(reply, marketplace, article),
    )


@router.get('/{marketplace}/search')
@inject
async def search_products(
    marketplace: Marketplace,
    query: str = Query(min_length=1, max_length=200, description='Текст поискового запроса'),
    page_key: str | None = Query(default=None, description='Ключ страницы из предыдущего ответа'),
    bus: DirectBus = Depends(Provide[DependencyContainer.direct_bus]),
    billing_service: BillingService = Depends(Provide[DependencyContainer.billing_service]),
    current_user: UserEntity = Depends(get_current_user),
) -> DirectSearchResponse:
    subject = query.strip()
    if not subject:
        raise invalid_search_query_error()
    cursor = decode_cursor(page_key, marketplace, subject)
    request = build_request(DirectRequestType.SEARCH, marketplace, subject, cursor)
    reply = await dispatch_request(bus, request)
    items = parse_reply_items(reply, ProductPayload)
    await charge_direct_request(billing_service, current_user.id, request, quantity=len(items))
    return DirectSearchResponse(
        request_id=reply.request_id,
        items=items,
        next_page_key=encode_next_page_key(reply, marketplace, subject),
    )


@router.get('/{marketplace}/category')
@inject
async def get_category_products(
    marketplace: Marketplace,
    url: str = Query(min_length=1, max_length=500, description='Ссылка на категорию маркетплейса'),
    page_key: str | None = Query(default=None, description='Ключ страницы из предыдущего ответа'),
    bus: DirectBus = Depends(Provide[DependencyContainer.direct_bus]),
    billing_service: BillingService = Depends(Provide[DependencyContainer.billing_service]),
    current_user: UserEntity = Depends(get_current_user),
) -> DirectCategoryResponse:
    subject = url.strip()
    if not subject:
        raise invalid_category_error()
    cursor = decode_cursor(page_key, marketplace, subject)
    request = build_request(DirectRequestType.CATEGORY, marketplace, subject, cursor)
    reply = await dispatch_request(bus, request)
    items = parse_reply_items(reply, ProductPayload)
    await charge_direct_request(billing_service, current_user.id, request, quantity=len(items))
    return DirectCategoryResponse(
        request_id=reply.request_id,
        items=items,
        next_page_key=encode_next_page_key(reply, marketplace, subject),
    )


@router.get('/{marketplace}/seller')
@inject
async def get_seller_products(
    marketplace: Marketplace,
    seller: str = Query(
        min_length=1,
        max_length=500,
        description='Числовой id продавца (только Wildberries) или ссылка на его витрину',
    ),
    page_key: str | None = Query(default=None, description='Ключ страницы из предыдущего ответа'),
    bus: DirectBus = Depends(Provide[DependencyContainer.direct_bus]),
    billing_service: BillingService = Depends(Provide[DependencyContainer.billing_service]),
    current_user: UserEntity = Depends(get_current_user),
) -> DirectSellerResponse:
    subject = seller.strip()
    if not subject:
        raise invalid_seller_error()
    cursor = decode_cursor(page_key, marketplace, subject)
    request = build_request(DirectRequestType.SELLER, marketplace, subject, cursor)
    reply = await dispatch_request(bus, request)
    items = parse_reply_items(reply, ProductPayload)
    await charge_direct_request(billing_service, current_user.id, request, quantity=len(items))
    return DirectSellerResponse(
        request_id=reply.request_id,
        items=items,
        next_page_key=encode_next_page_key(reply, marketplace, subject),
    )
