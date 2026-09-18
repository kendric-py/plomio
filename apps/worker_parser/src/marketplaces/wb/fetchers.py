from datetime import datetime
from urllib.parse import parse_qs, quote_plus, urlparse

from curl_cffi.requests import AsyncSession

from apps.worker_parser.src.entities import SessionMessage, WildberriesPaginationCursor
from apps.worker_parser.src.exceptions import InputResolutionError, UpstreamDataError
from apps.worker_parser.src.http_client import execute_request
from apps.worker_parser.src.marketplaces.wb.constants import (
    WB_BASE_URL,
    WB_CARD_API,
    WB_CARD_PARAMS,
    WB_CATEGORY_PARAMS_BASE,
    WB_FEEDBACK_HOST_API,
    WB_PAGE_SIZE,
    WB_RETRYABLE_STATUS_CODES,
    WB_SEARCH_API,
    WB_SEARCH_PARAMS_BASE,
    WB_SELLER_API,
    WB_SELLER_FILTERS_API,
    WB_SELLER_FILTERS_PARAMS_BASE,
    WB_SELLER_PARAMS_BASE,
    WB_SUPPLIER_CDN_URL,
    WB_SUPPLIER_METRICS_API,
)
from apps.worker_parser.src.marketplaces.wb.headers import (
    build_wb_api_headers,
    build_wb_cdn_headers,
    build_wb_navigation_headers,
)
from apps.worker_parser.src.marketplaces.wb.menu import load_wb_menu_search_queries
from apps.worker_parser.src.marketplaces.wb.parsers import (
    extract_wb_product_list,
    extract_wb_product_page,
    extract_wb_review_list,
)
from apps.worker_parser.src.marketplaces.wb.utils import (
    extract_wb_nm_id_from_url,
    extract_wb_size_option_id_from_url,
    extract_wb_supplier_id_from_url,
    get_raw_wb_products,
    get_wb_card_json_url,
    is_wb_blocked_response,
)
from core.enums import Marketplace
from packages.result.src.entities import (
    ProductPagePayload,
    ProductPayload,
    ReviewPayload,
    SellerCategoryPayload,
    SellerProfilePayload,
)


async def _wb_warmup(http_session: AsyncSession, session_message: SessionMessage) -> None:
    await execute_request(
        http_session,
        'GET',
        WB_BASE_URL + '/',
        extra_headers={**build_wb_navigation_headers(session_message), 'sec-fetch-site': 'none'},
        retryable_status_codes=WB_RETRYABLE_STATUS_CODES,
        is_blocked=is_wb_blocked_response,
    )


async def fetch_wb_search_page(
    query: str,
    cursor: WildberriesPaginationCursor | None,
    limit: int | None,
    seen_ids: set[int],
    http_session: AsyncSession,
    session_message: SessionMessage,
) -> tuple[list[ProductPayload], WildberriesPaginationCursor | None]:
    search_page_url = f'{WB_BASE_URL}/catalog/0/search.aspx?search={quote_plus(query)}'
    if cursor is None:
        await _wb_warmup(http_session, session_message)
        await execute_request(
            http_session,
            'GET',
            search_page_url,
            extra_headers={
                **build_wb_navigation_headers(session_message),
                'referer': WB_BASE_URL + '/',
                'sec-fetch-site': 'same-origin',
            },
            retryable_status_codes=WB_RETRYABLE_STATUS_CODES,
            is_blocked=is_wb_blocked_response,
        )
        cursor = WildberriesPaginationCursor(marketplace=Marketplace.WILDBERRIES, page_num=0)

    page_num = cursor.page_num + 1
    params = {**WB_SEARCH_PARAMS_BASE, 'query': query, 'page': str(page_num)}
    response = await execute_request(
        http_session,
        'GET',
        WB_SEARCH_API,
        params=params,
        extra_headers=build_wb_api_headers(session_message, search_page_url),
        retryable_status_codes=WB_RETRYABLE_STATUS_CODES,
        is_blocked=is_wb_blocked_response,
    )
    payload = response.json()
    products = extract_wb_product_list(payload, limit, seen_ids)
    raw_products = get_raw_wb_products(payload)

    if not raw_products or len(raw_products) < WB_PAGE_SIZE:
        return products, None
    if limit is not None and len(products) >= limit:
        return products, None
    return products, WildberriesPaginationCursor(
        marketplace=Marketplace.WILDBERRIES, page_num=page_num,
    )


async def fetch_wb_category_page(
    category_url: str,
    cursor: WildberriesPaginationCursor | None,
    limit: int | None,
    seen_ids: set[int],
    http_session: AsyncSession,
    session_message: SessionMessage,
) -> tuple[list[ProductPayload], WildberriesPaginationCursor | None]:
    parsed = urlparse(category_url)
    path = parsed.path.rstrip('/')
    url_params = {key: value[0] for key, value in parse_qs(parsed.query).items() if key != 'page'}
    base_category_url = WB_BASE_URL + path

    if cursor is None:
        menu_queries = await load_wb_menu_search_queries(http_session, session_message)
        search_query = menu_queries.get(path)
        if not search_query:
            raise InputResolutionError(f'Category not found in WB menu: {path}')

        await _wb_warmup(http_session, session_message)
        await execute_request(
            http_session,
            'GET',
            base_category_url,
            extra_headers={
                **build_wb_navigation_headers(session_message),
                'referer': WB_BASE_URL + '/',
                'sec-fetch-site': 'same-origin',
            },
            retryable_status_codes=WB_RETRYABLE_STATUS_CODES,
            is_blocked=is_wb_blocked_response,
        )
        if url_params:
            await execute_request(
                http_session,
                'GET',
                category_url,
                extra_headers={
                    **build_wb_navigation_headers(session_message),
                    'referer': base_category_url,
                    'sec-fetch-site': 'same-origin',
                },
                retryable_status_codes=WB_RETRYABLE_STATUS_CODES,
                is_blocked=is_wb_blocked_response,
            )
        cursor = WildberriesPaginationCursor(marketplace=Marketplace.WILDBERRIES, page_num=0)
    else:
        menu_queries = await load_wb_menu_search_queries(http_session, session_message)
        search_query = menu_queries.get(path)
        if not search_query:
            raise InputResolutionError(f'Category not found in WB menu: {path}')

    page_num = cursor.page_num + 1
    params = {**WB_CATEGORY_PARAMS_BASE, **url_params, 'query': search_query, 'page': str(page_num)}
    response = await execute_request(
        http_session,
        'GET',
        WB_SEARCH_API,
        params=params,
        extra_headers=build_wb_api_headers(session_message, category_url),
        retryable_status_codes=WB_RETRYABLE_STATUS_CODES,
        is_blocked=is_wb_blocked_response,
    )
    payload = response.json()
    products = extract_wb_product_list(payload, limit, seen_ids)
    raw_products = get_raw_wb_products(payload)

    if not raw_products or len(raw_products) < WB_PAGE_SIZE:
        return products, None
    if limit is not None and len(products) >= limit:
        return products, None
    return products, WildberriesPaginationCursor(
        marketplace=Marketplace.WILDBERRIES, page_num=page_num,
    )


async def fetch_wb_seller_page(
    seller_url: str,
    cursor: WildberriesPaginationCursor | None,
    limit: int | None,
    seen_ids: set[int],
    http_session: AsyncSession,
    session_message: SessionMessage,
) -> tuple[list[ProductPayload], WildberriesPaginationCursor | None]:
    supplier_id = extract_wb_supplier_id_from_url(seller_url)
    if supplier_id is None:
        raise InputResolutionError(f'Cannot extract supplier_id from URL: {seller_url!r}')
    seller_page_url = f'{WB_BASE_URL}/seller/{supplier_id}'

    if cursor is None:
        await _wb_warmup(http_session, session_message)
        await execute_request(
            http_session,
            'GET',
            seller_page_url,
            extra_headers={
                **build_wb_navigation_headers(session_message),
                'referer': WB_BASE_URL + '/',
                'sec-fetch-site': 'same-origin',
            },
            retryable_status_codes=WB_RETRYABLE_STATUS_CODES,
            is_blocked=is_wb_blocked_response,
        )
        cursor = WildberriesPaginationCursor(
            marketplace=Marketplace.WILDBERRIES, page_num=0, total_on_site=0, collected_so_far=0,
        )

    page_num = cursor.page_num + 1
    params = {**WB_SELLER_PARAMS_BASE, 'supplier': str(supplier_id), 'page': str(page_num)}
    response = await execute_request(
        http_session,
        'GET',
        WB_SELLER_API,
        params=params,
        extra_headers=build_wb_api_headers(session_message, seller_page_url),
        retryable_status_codes=WB_RETRYABLE_STATUS_CODES,
        is_blocked=is_wb_blocked_response,
    )
    payload = response.json()
    total_on_site = payload.get('total', 0) if page_num == 1 else (cursor.total_on_site or 0)
    products = extract_wb_product_list(payload, limit, seen_ids)
    raw_products = get_raw_wb_products(payload)
    collected_so_far = (cursor.collected_so_far or 0) + len(products)

    if not raw_products or len(raw_products) < WB_PAGE_SIZE or collected_so_far >= total_on_site:
        return products, None
    if limit is not None and len(products) >= limit:
        return products, None
    return products, WildberriesPaginationCursor(
        marketplace=Marketplace.WILDBERRIES,
        page_num=page_num,
        total_on_site=total_on_site,
        collected_so_far=collected_so_far,
    )


async def fetch_wb_product_page(
    product_url: str,
    http_session: AsyncSession,
    session_message: SessionMessage,
) -> ProductPagePayload:
    nm_id = extract_wb_nm_id_from_url(product_url)
    if nm_id is None:
        raise InputResolutionError(f'cannot extract nm_id from {product_url!r}')
    size_option_id = extract_wb_size_option_id_from_url(product_url)

    await execute_request(
        http_session,
        'GET',
        product_url,
        extra_headers={
            **build_wb_navigation_headers(session_message),
            'referer': WB_BASE_URL + '/',
            'sec-fetch-site': 'same-origin',
        },
        retryable_status_codes=WB_RETRYABLE_STATUS_CODES,
        is_blocked=is_wb_blocked_response,
    )
    card_api_response = await execute_request(
        http_session,
        'GET',
        WB_CARD_API,
        params={**WB_CARD_PARAMS, 'nm': str(nm_id)},
        extra_headers=build_wb_api_headers(session_message, product_url),
        retryable_status_codes=WB_RETRYABLE_STATUS_CODES,
        is_blocked=is_wb_blocked_response,
    )
    card_api_data = card_api_response.json()
    products = card_api_data.get('products') or []
    if not products:
        raise UpstreamDataError(f'card API returned no products for nm_id={nm_id}')
    card_api_product = products[0]

    card_json_url = get_wb_card_json_url(nm_id)
    card_json_response = await execute_request(
        http_session,
        'GET',
        card_json_url,
        extra_headers=build_wb_cdn_headers(session_message, product_url),
        retryable_status_codes=WB_RETRYABLE_STATUS_CODES,
        is_blocked=is_wb_blocked_response,
    )
    card_data = card_json_response.json()

    return extract_wb_product_page(card_data, card_api_product, nm_id, size_option_id)


async def fetch_wb_seller_profile(
    seller_url: str,
    http_session: AsyncSession,
    session_message: SessionMessage,
) -> SellerProfilePayload:
    supplier_id = extract_wb_supplier_id_from_url(seller_url)
    if supplier_id is None:
        raise InputResolutionError(f'Cannot extract supplier_id from URL: {seller_url!r}')
    seller_page_url = f'{WB_BASE_URL}/seller/{supplier_id}'

    cdn_url = WB_SUPPLIER_CDN_URL.format(supplier_id=supplier_id)
    cdn_response = await execute_request(
        http_session,
        'GET',
        cdn_url,
        extra_headers=build_wb_cdn_headers(session_message, seller_page_url),
        retryable_status_codes=WB_RETRYABLE_STATUS_CODES,
    )
    cdn_data = cdn_response.json()

    metrics_url = WB_SUPPLIER_METRICS_API.format(supplier_id=supplier_id)
    metrics_response = await execute_request(
        http_session,
        'GET',
        metrics_url,
        params={'curr': 'RUB'},
        extra_headers={
            **build_wb_cdn_headers(session_message, seller_page_url), 'x-client-name': 'site',
        },
        retryable_status_codes=WB_RETRYABLE_STATUS_CODES,
    )
    metrics_data = metrics_response.json()

    filters_response = await execute_request(
        http_session,
        'GET',
        WB_SELLER_FILTERS_API,
        params={**WB_SELLER_FILTERS_PARAMS_BASE, 'supplier': str(supplier_id)},
        extra_headers=build_wb_api_headers(session_message, seller_page_url),
        retryable_status_codes=WB_RETRYABLE_STATUS_CODES,
        is_blocked=is_wb_blocked_response,
    )
    filters_data = filters_response.json()

    categories: list[SellerCategoryPayload] = []
    data_block = filters_data.get('data') or {}
    filters_list = data_block.get('filters') or []
    if filters_list:
        for item in filters_list[0].get('items') or []:
            categories.append(
                SellerCategoryPayload(
                    category_id=item.get('id', 0),
                    name=item.get('name', ''),
                    parent_name=item.get('parentName'),
                ),
            )
    total_products: int | None = data_block.get('total')

    registration_date: datetime | None = None
    registration_date_str: str | None = metrics_data.get('registrationDate')
    if registration_date_str:
        try:
            registration_date = datetime.fromisoformat(registration_date_str.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            pass

    return SellerProfilePayload(
        supplier_id=supplier_id,
        name=cdn_data.get('supplierName'),
        full_name=cdn_data.get('supplierFullName'),
        trademark=cdn_data.get('trademark'),
        inn=cdn_data.get('inn'),
        ogrnip=cdn_data.get('ogrnip'),
        kpp=cdn_data.get('kpp'),
        rating=metrics_data.get('valuation'),
        feedbacks_count=metrics_data.get('feedbacksCount'),
        registration_date=registration_date,
        sale_item_quantity=metrics_data.get('saleItemQuantity'),
        delivery_duration=metrics_data.get('deliveryDuration'),
        is_premium=metrics_data.get('isPremium'),
        is_deleted=metrics_data.get('isDeleted'),
        deactivated=metrics_data.get('deactivated'),
        categories=categories,
        total_products=total_products,
        seller_url=seller_url,
    )


async def fetch_wb_review_page(
    product_url: str,
    http_session: AsyncSession,
    session_message: SessionMessage,
) -> list[ReviewPayload]:
    nm_id = extract_wb_nm_id_from_url(product_url)
    if nm_id is None:
        raise InputResolutionError(f'cannot extract nm_id from {product_url!r}')

    await _wb_warmup(http_session, session_message)
    await execute_request(
        http_session,
        'GET',
        product_url,
        extra_headers={
            **build_wb_navigation_headers(session_message),
            'referer': WB_BASE_URL + '/',
            'sec-fetch-site': 'same-origin',
        },
        retryable_status_codes=WB_RETRYABLE_STATUS_CODES,
        is_blocked=is_wb_blocked_response,
    )

    card_response = await execute_request(
        http_session,
        'GET',
        WB_CARD_API,
        params={**WB_CARD_PARAMS, 'nm': str(nm_id)},
        extra_headers=build_wb_api_headers(session_message, product_url),
        retryable_status_codes=WB_RETRYABLE_STATUS_CODES,
        is_blocked=is_wb_blocked_response,
    )
    products = card_response.json().get('products') or []
    if not products:
        raise UpstreamDataError(f'card API returned no products for nm_id={nm_id}')
    root_id = int(products[0]['root'])

    feedback_host_response = await execute_request(
        http_session,
        'GET',
        WB_FEEDBACK_HOST_API,
        params={'imt': str(root_id)},
        extra_headers=build_wb_cdn_headers(session_message, product_url),
        retryable_status_codes=WB_RETRYABLE_STATUS_CODES,
        is_blocked=is_wb_blocked_response,
    )
    hosts: list[str] = feedback_host_response.json()
    if not hosts:
        raise UpstreamDataError(f'feedback host API returned empty list for root_id={root_id}')
    feedback_host = hosts[0]

    feedback_url = f'{feedback_host}/feedbacks/v2/{root_id}'
    feedback_response = await execute_request(
        http_session,
        'GET',
        feedback_url,
        extra_headers=build_wb_cdn_headers(session_message, product_url),
        retryable_status_codes=WB_RETRYABLE_STATUS_CODES,
        is_blocked=is_wb_blocked_response,
    )
    payload = feedback_response.json()
    seen_uuids: set[str] = set()
    reviews, _ = extract_wb_review_list(payload, seen_uuids)
    return reviews
