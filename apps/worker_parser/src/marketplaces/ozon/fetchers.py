import json
from urllib.parse import quote_plus, urlparse

from apps.worker_parser.src.entities import OzonPaginationCursor, OzonReviewCursor, Page
from apps.worker_parser.src.fetch_context import FetchContext
from apps.worker_parser.src.marketplaces.ozon.constants import (
    OZON_API_TIMEOUT,
    OZON_BASE_URL,
    OZON_RETRYABLE_STATUS_CODES,
    OZON_SEARCH_API,
    OZON_LISTING_BASE_DELAY,
    OZON_LISTING_HTTP_RETRIES,
    OZON_REVIEW_SORT_ORDERS,
)
from apps.worker_parser.src.marketplaces.ozon.headers import (
    build_ozon_api_headers,
    build_ozon_navigation_headers,
)
from apps.worker_parser.src.marketplaces.ozon.pagination import extract_ozon_next_page
from apps.worker_parser.src.marketplaces.ozon.parsers import (
    extract_ozon_product_list,
    extract_ozon_product_page,
    extract_ozon_review_list,
    extract_ozon_seller_id_from_widget_states,
    extract_ozon_seller_profile,
)
from apps.worker_parser.src.marketplaces.ozon.utils import (
    extract_ozon_product_id_from_path,
    extract_ozon_product_path_from_url,
    is_ozon_blocked_response,
)
from core.enums import Marketplace
from packages.result.src.entities import (
    ProductPagePayload,
    ProductPayload,
    ReviewPayload,
    SellerProfilePayload,
)


async def _fetch_ozon_listing_warmup_cursor(
    warmup_url: str,
    initial_relative_url: str,
    ctx: FetchContext,
) -> OzonPaginationCursor:
    warmup_response = await ctx.request(
        'GET',
        warmup_url,
        extra_headers={
            **build_ozon_navigation_headers(ctx.session_message),
            'referer': OZON_BASE_URL + '/',
            'sec-fetch-site': 'same-origin',
        },
        retryable_status_codes=OZON_RETRYABLE_STATUS_CODES,
        is_blocked=is_ozon_blocked_response,
    )
    return OzonPaginationCursor(
        marketplace=Marketplace.OZON,
        next_url=initial_relative_url,
        referer=str(warmup_response.url),
        prev_request_id=None,
    )


async def _fetch_ozon_listing_page(
    cursor: OzonPaginationCursor,
    ctx: FetchContext,
) -> Page[ProductPayload]:
    extra_headers = build_ozon_api_headers(ctx.session_message, cursor.referer)
    if cursor.prev_request_id:
        extra_headers['x-o3-parent-requestid'] = cursor.prev_request_id

    response = await ctx.request(
        'GET',
        OZON_SEARCH_API,
        params={'url': cursor.next_url},
        extra_headers=extra_headers,
        timeout=OZON_API_TIMEOUT,
        retries=OZON_LISTING_HTTP_RETRIES,
        base_delay=OZON_LISTING_BASE_DELAY,
        retryable_status_codes=OZON_RETRYABLE_STATUS_CODES,
        is_blocked=is_ozon_blocked_response,
    )
    payload = response.json()
    products = extract_ozon_product_list(payload, ctx.limit, ctx.seen_keys)

    next_url = extract_ozon_next_page(payload)
    if next_url is None or (ctx.limit is not None and len(products) >= ctx.limit):
        return Page(items=products)

    current_page_url: str = payload.get('pageInfo', {}).get('url', '')
    return Page(
        items=products,
        next_cursor=OzonPaginationCursor(
            marketplace=Marketplace.OZON,
            next_url=next_url,
            referer=OZON_BASE_URL + current_page_url,
            prev_request_id=payload.get('requestID'),
        ),
    )


async def fetch_ozon_search_page(
    query: str,
    cursor: OzonPaginationCursor | None,
    ctx: FetchContext,
) -> Page[ProductPayload]:
    if cursor is None:
        cursor = await _fetch_ozon_listing_warmup_cursor(
            warmup_url=f'{OZON_BASE_URL}/search/?from_global=true&text={quote_plus(query)}',
            initial_relative_url=f'/search/?from_global=true&text={quote_plus(query)}',
            ctx=ctx,
        )
    return await _fetch_ozon_listing_page(cursor, ctx)


async def fetch_ozon_category_page(
    category_url: str,
    cursor: OzonPaginationCursor | None,
    ctx: FetchContext,
) -> Page[ProductPayload]:
    if cursor is None:
        parsed = urlparse(category_url)
        category_path = parsed.path.rstrip('/') + '/'
        query_string = ('?' + parsed.query) if parsed.query else ''
        cursor = await _fetch_ozon_listing_warmup_cursor(
            warmup_url=OZON_BASE_URL + category_path + query_string,
            initial_relative_url=category_path + query_string,
            ctx=ctx,
        )
    return await _fetch_ozon_listing_page(cursor, ctx)


async def fetch_ozon_seller_page(
    seller_url: str,
    cursor: OzonPaginationCursor | None,
    ctx: FetchContext,
) -> Page[ProductPayload]:
    if cursor is None:
        seller_path = urlparse(seller_url).path.rstrip('/') + '/'
        cursor = await _fetch_ozon_listing_warmup_cursor(
            warmup_url=OZON_BASE_URL + seller_path,
            initial_relative_url=seller_path,
            ctx=ctx,
        )
    return await _fetch_ozon_listing_page(cursor, ctx)


async def fetch_ozon_product_page(
    product_url: str,
    cursor: None,
    ctx: FetchContext,
) -> Page[ProductPagePayload]:
    product_path = extract_ozon_product_path_from_url(product_url)
    product_id = extract_ozon_product_id_from_path(product_path)

    page1_response = await ctx.request(
        'GET',
        OZON_SEARCH_API,
        params={'url': product_path},
        extra_headers=build_ozon_api_headers(ctx.session_message, OZON_BASE_URL + '/'),
        retryable_status_codes=OZON_RETRYABLE_STATUS_CODES,
        is_blocked=is_ozon_blocked_response,
    )
    page1_payload = page1_response.json()
    start_page_id: str = page1_payload.get('requestID', '')

    page2_relative_url = (
        f'{product_path}?layout_container=pdpPage2column'
        f'&layout_page_index=2&start_page_id={start_page_id}'
    )
    page2_extra_headers = build_ozon_api_headers(ctx.session_message, OZON_BASE_URL + product_path)
    page2_extra_headers['x-o3-parent-requestid'] = start_page_id
    page2_response = await ctx.request(
        'GET',
        OZON_SEARCH_API,
        params={'url': page2_relative_url},
        extra_headers=page2_extra_headers,
        retryable_status_codes=OZON_RETRYABLE_STATUS_CODES,
        is_blocked=is_ozon_blocked_response,
    )
    page2_payload = page2_response.json()

    return Page(
        items=[
            extract_ozon_product_page(
                page1_payload, page2_payload, OZON_BASE_URL + product_path, product_id,
            ),
        ],
    )


async def fetch_ozon_seller_profile(
    seller_url: str,
    ctx: FetchContext,
) -> SellerProfilePayload:
    seller_path = urlparse(seller_url).path.rstrip('/') + '/'

    main_response = await ctx.request(
        'GET',
        OZON_SEARCH_API,
        params={'url': seller_path},
        extra_headers=build_ozon_api_headers(ctx.session_message, OZON_BASE_URL + seller_path),
        timeout=OZON_API_TIMEOUT,
        retryable_status_codes=OZON_RETRYABLE_STATUS_CODES,
        is_blocked=is_ozon_blocked_response,
    )
    main_payload = main_response.json()
    seller_id = extract_ozon_seller_id_from_widget_states(main_payload.get('widgetStates', {}))

    modal_url = f'/modal/shop-in-shop-info?seller_id={seller_id}'
    modal_response = await ctx.request(
        'GET',
        OZON_SEARCH_API,
        params={'url': modal_url},
        extra_headers=build_ozon_api_headers(ctx.session_message, OZON_BASE_URL + seller_path),
        timeout=OZON_API_TIMEOUT,
        retryable_status_codes=OZON_RETRYABLE_STATUS_CODES,
        is_blocked=is_ozon_blocked_response,
    )
    modal_payload = modal_response.json()

    return extract_ozon_seller_profile(
        main_payload.get('widgetStates', {}), modal_payload.get('widgetStates', {}), seller_url,
    )


def _extract_review_next_params(payload: dict) -> str:
    for key, raw in payload.get('widgetStates', {}).items():
        if 'webListReviews' in key and isinstance(raw, str):
            return json.loads(raw).get('paging', {}).get('nextButton') or ''
    return ''


def _next_review_sort_cursor(
    cursor: OzonReviewCursor,
    ctx: FetchContext,
) -> OzonReviewCursor | None:
    if not ctx.walk_all_review_sorts:
        return None
    sort_orders = list(OZON_REVIEW_SORT_ORDERS)
    current_index = (
        sort_orders.index(cursor.sort_order) if cursor.sort_order in sort_orders else -1
    )
    if current_index + 1 >= len(sort_orders):
        return None
    return OzonReviewCursor(
        marketplace=Marketplace.OZON,
        sort_order=sort_orders[current_index + 1],
        next_params=None,
        seen_uuids=list(ctx.seen_keys),
    )


async def fetch_ozon_review_page(
    product_url: str,
    cursor: OzonReviewCursor | None,
    ctx: FetchContext,
) -> Page[ReviewPayload]:
    """Одна страница (30 отзывов) `{product}/reviews/?...` — без прогрева. Ссылка на следующую
    страницу берётся из `paging.nextButton` (с `page_key`), а не собирается из номера — иначе
    Ozon глубже ~5-й страницы отдаёт повторы. Потолок Ozon — около 33 страниц на сортировку, для
    полноты режим задач обходит сортировки из `OZON_REVIEW_SORT_ORDERS`."""
    product_path = extract_ozon_product_path_from_url(product_url)
    if cursor is None:
        cursor = OzonReviewCursor(
            marketplace=Marketplace.OZON, sort_order=OZON_REVIEW_SORT_ORDERS[0],
        )
    params_suffix = cursor.next_params or f'?sort={cursor.sort_order}'

    response = await ctx.request(
        'GET',
        OZON_SEARCH_API,
        params={'url': f'{product_path}reviews/{params_suffix}'},
        extra_headers=build_ozon_api_headers(ctx.session_message, OZON_BASE_URL + product_path),
        timeout=OZON_API_TIMEOUT,
        retryable_status_codes=OZON_RETRYABLE_STATUS_CODES,
        is_blocked=is_ozon_blocked_response,
    )
    payload = response.json()
    reviews, _ = extract_ozon_review_list(payload, ctx.seen_keys)

    next_params = _extract_review_next_params(payload)
    if next_params and reviews:
        return Page(
            items=reviews,
            next_cursor=OzonReviewCursor(
                marketplace=Marketplace.OZON,
                sort_order=cursor.sort_order,
                next_params=next_params,
                seen_uuids=list(ctx.seen_keys) if ctx.walk_all_review_sorts else [],
            ),
        )
    return Page(items=reviews, next_cursor=_next_review_sort_cursor(cursor, ctx))
