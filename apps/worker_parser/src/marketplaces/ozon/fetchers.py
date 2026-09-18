from urllib.parse import quote_plus, urlparse

from curl_cffi.requests import AsyncSession

from apps.worker_parser.src.entities import OzonPaginationCursor, OzonReviewCursor, SessionMessage
from apps.worker_parser.src.http_client import execute_request
from apps.worker_parser.src.marketplaces.ozon.constants import (
    OZON_API_TIMEOUT,
    OZON_BASE_URL,
    OZON_RETRYABLE_STATUS_CODES,
    OZON_SEARCH_API,
    OzonReviewSortOrder,
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
    http_session: AsyncSession,
    session_message: SessionMessage,
) -> OzonPaginationCursor:
    warmup_response = await execute_request(
        http_session,
        'GET',
        warmup_url,
        extra_headers={
            **build_ozon_navigation_headers(session_message),
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
    limit: int | None,
    seen_keys: set[str],
    http_session: AsyncSession,
    session_message: SessionMessage,
) -> tuple[list[ProductPayload], OzonPaginationCursor | None]:
    extra_headers = build_ozon_api_headers(session_message, cursor.referer)
    if cursor.prev_request_id:
        extra_headers['x-o3-parent-requestid'] = cursor.prev_request_id

    response = await execute_request(
        http_session,
        'GET',
        OZON_SEARCH_API,
        params={'url': cursor.next_url},
        extra_headers=extra_headers,
        timeout=OZON_API_TIMEOUT,
        retries=2,
        base_delay=0.5,
        retryable_status_codes=OZON_RETRYABLE_STATUS_CODES,
        is_blocked=is_ozon_blocked_response,
    )
    payload = response.json()
    products = extract_ozon_product_list(payload, limit, seen_keys)

    next_url = extract_ozon_next_page(payload)
    if next_url is None or (limit is not None and len(products) >= limit):
        return products, None

    current_page_url: str = payload.get('pageInfo', {}).get('url', '')
    return products, OzonPaginationCursor(
        marketplace=Marketplace.OZON,
        next_url=next_url,
        referer=OZON_BASE_URL + current_page_url,
        prev_request_id=payload.get('requestID'),
    )


async def fetch_ozon_search_page(
    query: str,
    cursor: OzonPaginationCursor | None,
    limit: int | None,
    seen_keys: set[str],
    http_session: AsyncSession,
    session_message: SessionMessage,
) -> tuple[list[ProductPayload], OzonPaginationCursor | None]:
    if cursor is None:
        cursor = await _fetch_ozon_listing_warmup_cursor(
            warmup_url=f'{OZON_BASE_URL}/search/?from_global=true&text={quote_plus(query)}',
            initial_relative_url=f'/search/?from_global=true&text={quote_plus(query)}',
            http_session=http_session,
            session_message=session_message,
        )
    return await _fetch_ozon_listing_page(cursor, limit, seen_keys, http_session, session_message)


async def fetch_ozon_category_page(
    category_url: str,
    cursor: OzonPaginationCursor | None,
    limit: int | None,
    seen_keys: set[str],
    http_session: AsyncSession,
    session_message: SessionMessage,
) -> tuple[list[ProductPayload], OzonPaginationCursor | None]:
    if cursor is None:
        parsed = urlparse(category_url)
        category_path = parsed.path.rstrip('/') + '/'
        query_string = ('?' + parsed.query) if parsed.query else ''
        cursor = await _fetch_ozon_listing_warmup_cursor(
            warmup_url=OZON_BASE_URL + category_path + query_string,
            initial_relative_url=category_path + query_string,
            http_session=http_session,
            session_message=session_message,
        )
    return await _fetch_ozon_listing_page(cursor, limit, seen_keys, http_session, session_message)


async def fetch_ozon_seller_page(
    seller_url: str,
    cursor: OzonPaginationCursor | None,
    limit: int | None,
    seen_keys: set[str],
    http_session: AsyncSession,
    session_message: SessionMessage,
) -> tuple[list[ProductPayload], OzonPaginationCursor | None]:
    if cursor is None:
        seller_path = urlparse(seller_url).path.rstrip('/') + '/'
        cursor = await _fetch_ozon_listing_warmup_cursor(
            warmup_url=OZON_BASE_URL + seller_path,
            initial_relative_url=seller_path,
            http_session=http_session,
            session_message=session_message,
        )
    return await _fetch_ozon_listing_page(cursor, limit, seen_keys, http_session, session_message)


async def fetch_ozon_product_page(
    product_url: str,
    http_session: AsyncSession,
    session_message: SessionMessage,
) -> ProductPagePayload:
    product_path = extract_ozon_product_path_from_url(product_url)
    product_id = extract_ozon_product_id_from_path(product_path)

    page1_response = await execute_request(
        http_session,
        'GET',
        OZON_SEARCH_API,
        params={'url': product_path},
        extra_headers=build_ozon_api_headers(session_message, OZON_BASE_URL + '/'),
        retryable_status_codes=OZON_RETRYABLE_STATUS_CODES,
        is_blocked=is_ozon_blocked_response,
    )
    page1_payload = page1_response.json()
    start_page_id: str = page1_payload.get('requestID', '')

    page2_relative_url = (
        f'{product_path}?layout_container=pdpPage2column'
        f'&layout_page_index=2&start_page_id={start_page_id}'
    )
    page2_extra_headers = build_ozon_api_headers(session_message, OZON_BASE_URL + product_path)
    page2_extra_headers['x-o3-parent-requestid'] = start_page_id
    page2_response = await execute_request(
        http_session,
        'GET',
        OZON_SEARCH_API,
        params={'url': page2_relative_url},
        extra_headers=page2_extra_headers,
        retryable_status_codes=OZON_RETRYABLE_STATUS_CODES,
        is_blocked=is_ozon_blocked_response,
    )
    page2_payload = page2_response.json()

    return extract_ozon_product_page(
        page1_payload, page2_payload, OZON_BASE_URL + product_path, product_id,
    )


async def fetch_ozon_seller_profile(
    seller_url: str,
    http_session: AsyncSession,
    session_message: SessionMessage,
) -> SellerProfilePayload:
    seller_path = urlparse(seller_url).path.rstrip('/') + '/'

    main_response = await execute_request(
        http_session,
        'GET',
        OZON_SEARCH_API,
        params={'url': seller_path},
        extra_headers=build_ozon_api_headers(session_message, OZON_BASE_URL + seller_path),
        timeout=OZON_API_TIMEOUT,
        retryable_status_codes=OZON_RETRYABLE_STATUS_CODES,
        is_blocked=is_ozon_blocked_response,
    )
    main_payload = main_response.json()
    seller_id = extract_ozon_seller_id_from_widget_states(main_payload.get('widgetStates', {}))

    modal_url = f'/modal/shop-in-shop-info?seller_id={seller_id}'
    modal_response = await execute_request(
        http_session,
        'GET',
        OZON_SEARCH_API,
        params={'url': modal_url},
        extra_headers=build_ozon_api_headers(session_message, OZON_BASE_URL + seller_path),
        timeout=OZON_API_TIMEOUT,
        retryable_status_codes=OZON_RETRYABLE_STATUS_CODES,
        is_blocked=is_ozon_blocked_response,
    )
    modal_payload = modal_response.json()

    return extract_ozon_seller_profile(
        main_payload.get('widgetStates', {}), modal_payload.get('widgetStates', {}), seller_url,
    )


async def fetch_ozon_review_page(
    product_url: str,
    cursor: OzonReviewCursor | None,
    seen_uuids: set[str],
    http_session: AsyncSession,
    session_message: SessionMessage,
) -> tuple[list[ReviewPayload], OzonReviewCursor | None]:
    if cursor is None:
        product_path = extract_ozon_product_path_from_url(product_url)
        await execute_request(
            http_session,
            'GET',
            OZON_BASE_URL + '/',
            extra_headers={
                **build_ozon_navigation_headers(session_message), 'sec-fetch-site': 'none',
            },
            retryable_status_codes=OZON_RETRYABLE_STATUS_CODES,
            is_blocked=is_ozon_blocked_response,
        )
        product_response = await execute_request(
            http_session,
            'GET',
            OZON_SEARCH_API,
            params={'url': product_path},
            extra_headers=build_ozon_api_headers(session_message, OZON_BASE_URL + '/'),
            timeout=OZON_API_TIMEOUT,
            retryable_status_codes=OZON_RETRYABLE_STATUS_CODES,
            is_blocked=is_ozon_blocked_response,
        )
        start_page_id: str = product_response.json().get('requestID', '')
        first_sort_order = list(OzonReviewSortOrder)[0]
        cursor = OzonReviewCursor(
            marketplace=Marketplace.OZON,
            product_path=product_path,
            start_page_id=start_page_id,
            sort_order=first_sort_order.value,
            next_url=(
                f'{product_path}?layout_container=reviewshelfpaginator'
                f'&layout_page_index=1&sort={first_sort_order.value}&start_page_id={start_page_id}'
            ),
            referer=OZON_BASE_URL + product_path,
            prev_request_id=start_page_id,
            seen_uuids=[],
        )

    extra_headers = build_ozon_api_headers(session_message, cursor.referer)
    if cursor.prev_request_id:
        extra_headers['x-o3-parent-requestid'] = cursor.prev_request_id

    response = await execute_request(
        http_session,
        'GET',
        OZON_SEARCH_API,
        params={'url': cursor.next_url},
        extra_headers=extra_headers,
        timeout=OZON_API_TIMEOUT,
        retryable_status_codes=OZON_RETRYABLE_STATUS_CODES,
        is_blocked=is_ozon_blocked_response,
    )
    payload = response.json()
    reviews, _ = extract_ozon_review_list(payload, seen_uuids)

    next_url = payload.get('nextPage')
    if next_url:
        current_page_url: str = payload.get('pageInfo', {}).get('url', '')
        return reviews, OzonReviewCursor(
            marketplace=Marketplace.OZON,
            product_path=cursor.product_path,
            start_page_id=cursor.start_page_id,
            sort_order=cursor.sort_order,
            next_url=next_url,
            referer=OZON_BASE_URL + current_page_url,
            prev_request_id=payload.get('requestID'),
            seen_uuids=list(seen_uuids),
        )

    sort_orders = list(OzonReviewSortOrder)
    current_sort_index = [sort_order.value for sort_order in sort_orders].index(cursor.sort_order)
    if current_sort_index + 1 >= len(sort_orders):
        return reviews, None

    next_sort_order = sort_orders[current_sort_index + 1]
    return reviews, OzonReviewCursor(
        marketplace=Marketplace.OZON,
        product_path=cursor.product_path,
        start_page_id=cursor.start_page_id,
        sort_order=next_sort_order.value,
        next_url=(
            f'{cursor.product_path}?layout_container=reviewshelfpaginator'
            f'&layout_page_index=1&sort={next_sort_order.value}'
            f'&start_page_id={cursor.start_page_id}'
        ),
        referer=OZON_BASE_URL + cursor.product_path,
        prev_request_id=cursor.start_page_id,
        seen_uuids=list(seen_uuids),
    )
