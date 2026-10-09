from datetime import datetime
from urllib.parse import parse_qs, quote_plus, urlparse

from apps.worker_parser.src.entities import Page, WbReviewCursor, WildberriesPaginationCursor
from apps.worker_parser.src.exceptions import (
    EmptyPageUnconfirmedError,
    InputResolutionError,
    RequestError,
    SuspiciousThinResultError,
    UpstreamDataError,
)
from apps.worker_parser.src.fetch_context import FetchContext
from apps.worker_parser.src.marketplaces.wb.constants import (
    WB_BASE_URL,
    WB_CARD_API,
    WB_CARD_PARAMS,
    WB_CATEGORY_PARAMS_BASE,
    WB_FEEDBACK_HOST_API,
    WB_PAGE_SIZE,
    WB_RETRYABLE_STATUS_CODES,
    WB_SEARCH_API,
    WB_SEARCH_PAGE_LIMIT_ERROR,
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
    get_wb_basket_host_candidates,
    get_wb_card_json_url,
    is_degraded_wb_listing,
    is_wb_blocked_response,
    remember_wb_basket_host,
)
from core.enums import Marketplace
from packages.result.src.entities import (
    ProductPagePayload,
    ProductPayload,
    ReviewPayload,
    SellerCategoryPayload,
    SellerProfilePayload,
)


async def _wb_warmup(ctx: FetchContext) -> None:
    await ctx.request(
        'GET',
        WB_BASE_URL + '/',
        extra_headers={
            **build_wb_navigation_headers(ctx.session_message), 'sec-fetch-site': 'none',
        },
        retryable_status_codes=WB_RETRYABLE_STATUS_CODES,
        is_blocked=is_wb_blocked_response,
    )


def _guard_listing_payload(payload: dict, ctx: FetchContext, what: str) -> None:
    """Сбои страницы выдачи WB (поиск, категория, продавец) — не конец выдачи:
    - деградировавший ответ сессии (1 посторонний товар) → смена сессии и повтор страницы;
    - первая пустая страница → проверка на другой сессии (`confirm_empty_page`); пустота и там —
      настоящий конец. Повторы на той же сессии не помогают (проверено на живых ответах)."""
    if is_degraded_wb_listing(payload):
        raise SuspiciousThinResultError(f'degraded WB {what} response')
    if 'products' in payload and not payload['products'] and not ctx.confirm_empty_page:
        raise EmptyPageUnconfirmedError(f'empty WB {what} page, needs confirmation')


def _end_of_search_or_fail(payload: dict, query: str) -> Page[ProductPayload]:
    """Ответ-ошибка на страницу больше лимита WB — конец выдачи. Любая другая ошибка в теле
    (HTTP при этом 200) — не конец, а сбой: молча оборвать выдачу нельзя."""
    if WB_SEARCH_PAGE_LIMIT_ERROR in str(payload.get('error')):
        return Page(items=[])
    raise UpstreamDataError(f'WB search returned error for {query!r}: {payload.get("error")}')


async def fetch_wb_search_page(
    query: str,
    cursor: WildberriesPaginationCursor | None,
    ctx: FetchContext,
) -> Page[ProductPayload]:
    search_page_url = f'{WB_BASE_URL}/catalog/0/search.aspx?search={quote_plus(query)}'
    if cursor is None:
        await _wb_warmup(ctx)
        await ctx.request(
            'GET',
            search_page_url,
            extra_headers={
                **build_wb_navigation_headers(ctx.session_message),
                'referer': WB_BASE_URL + '/',
                'sec-fetch-site': 'same-origin',
            },
            retryable_status_codes=WB_RETRYABLE_STATUS_CODES,
            is_blocked=is_wb_blocked_response,
        )
        cursor = WildberriesPaginationCursor(marketplace=Marketplace.WILDBERRIES, page_num=0)

    page_num = cursor.page_num + 1
    params = {**WB_SEARCH_PARAMS_BASE, 'query': query, 'page': str(page_num)}
    response = await ctx.request(
        'GET',
        WB_SEARCH_API,
        params=params,
        extra_headers=build_wb_api_headers(ctx.session_message, search_page_url),
        retryable_status_codes=WB_RETRYABLE_STATUS_CODES,
        is_blocked=is_wb_blocked_response,
    )
    payload = response.json()
    if 'error' in payload:
        return _end_of_search_or_fail(payload, query)
    _guard_listing_payload(payload, ctx, 'search')
    products = extract_wb_product_list(payload, ctx.limit, ctx.seen_keys)

    if not get_raw_wb_products(payload):
        return Page(items=products)
    if ctx.limit is not None and len(products) >= ctx.limit:
        return Page(items=products)
    return Page(
        items=products,
        next_cursor=WildberriesPaginationCursor(
            marketplace=Marketplace.WILDBERRIES, page_num=page_num,
        ),
    )


async def fetch_wb_category_page(
    category_url: str,
    cursor: WildberriesPaginationCursor | None,
    ctx: FetchContext,
) -> Page[ProductPayload]:
    parsed = urlparse(category_url)
    path = parsed.path.rstrip('/')
    url_params = {key: value[0] for key, value in parse_qs(parsed.query).items() if key != 'page'}
    base_category_url = WB_BASE_URL + path

    if cursor is None:
        menu_queries = await load_wb_menu_search_queries(ctx.http_session, ctx.session_message)
        search_query = menu_queries.get(path)
        if not search_query:
            raise InputResolutionError(f'Category not found in WB menu: {path}')

        await _wb_warmup(ctx)
        await ctx.request(
            'GET',
            base_category_url,
            extra_headers={
                **build_wb_navigation_headers(ctx.session_message),
                'referer': WB_BASE_URL + '/',
                'sec-fetch-site': 'same-origin',
            },
            retryable_status_codes=WB_RETRYABLE_STATUS_CODES,
            is_blocked=is_wb_blocked_response,
        )
        if url_params:
            await ctx.request(
                'GET',
                category_url,
                extra_headers={
                    **build_wb_navigation_headers(ctx.session_message),
                    'referer': base_category_url,
                    'sec-fetch-site': 'same-origin',
                },
                retryable_status_codes=WB_RETRYABLE_STATUS_CODES,
                is_blocked=is_wb_blocked_response,
            )
        cursor = WildberriesPaginationCursor(marketplace=Marketplace.WILDBERRIES, page_num=0)
    else:
        menu_queries = await load_wb_menu_search_queries(ctx.http_session, ctx.session_message)
        search_query = menu_queries.get(path)
        if not search_query:
            raise InputResolutionError(f'Category not found in WB menu: {path}')

    page_num = cursor.page_num + 1
    params = {**WB_CATEGORY_PARAMS_BASE, **url_params, 'query': search_query, 'page': str(page_num)}
    response = await ctx.request(
        'GET',
        WB_SEARCH_API,
        params=params,
        extra_headers=build_wb_api_headers(ctx.session_message, category_url),
        retryable_status_codes=WB_RETRYABLE_STATUS_CODES,
        is_blocked=is_wb_blocked_response,
    )
    payload = response.json()
    _guard_listing_payload(payload, ctx, 'category')
    products = extract_wb_product_list(payload, ctx.limit, ctx.seen_keys)
    raw_products = get_raw_wb_products(payload)

    if not raw_products or len(raw_products) < WB_PAGE_SIZE:
        return Page(items=products)
    if ctx.limit is not None and len(products) >= ctx.limit:
        return Page(items=products)
    return Page(
        items=products,
        next_cursor=WildberriesPaginationCursor(
            marketplace=Marketplace.WILDBERRIES, page_num=page_num,
        ),
    )


async def fetch_wb_seller_page(
    seller_url: str,
    cursor: WildberriesPaginationCursor | None,
    ctx: FetchContext,
) -> Page[ProductPayload]:
    supplier_id = extract_wb_supplier_id_from_url(seller_url)
    if supplier_id is None:
        raise InputResolutionError(f'Cannot extract supplier_id from URL: {seller_url!r}')
    seller_page_url = f'{WB_BASE_URL}/seller/{supplier_id}'

    if cursor is None:
        await _wb_warmup(ctx)
        await ctx.request(
            'GET',
            seller_page_url,
            extra_headers={
                **build_wb_navigation_headers(ctx.session_message),
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
    response = await ctx.request(
        'GET',
        WB_SELLER_API,
        params=params,
        extra_headers=build_wb_api_headers(ctx.session_message, seller_page_url),
        retryable_status_codes=WB_RETRYABLE_STATUS_CODES,
        is_blocked=is_wb_blocked_response,
    )
    payload = response.json()
    _guard_listing_payload(payload, ctx, 'seller')
    total_on_site = payload.get('total', 0) if page_num == 1 else (cursor.total_on_site or 0)
    products = extract_wb_product_list(payload, ctx.limit, ctx.seen_keys)
    raw_products = get_raw_wb_products(payload)
    collected_so_far = (cursor.collected_so_far or 0) + len(products)

    if not raw_products or len(raw_products) < WB_PAGE_SIZE or collected_so_far >= total_on_site:
        return Page(items=products)
    if ctx.limit is not None and len(products) >= ctx.limit:
        return Page(items=products)
    return Page(
        items=products,
        next_cursor=WildberriesPaginationCursor(
            marketplace=Marketplace.WILDBERRIES,
            page_num=page_num,
            total_on_site=total_on_site,
            collected_so_far=collected_so_far,
        ),
    )


async def _fetch_wb_card_json(nm_id: int, product_url: str, ctx: FetchContext) -> dict:
    """`card.json` лежит на CDN-корзине, номер которой выводится из `nm_id` по таблице диапазонов;
    таблица отстаёт от WB (новые корзины), и на неверном хосте — 404. Поэтому при 404 пробуем
    соседние корзины, найденную запоминаем (`remember_wb_basket_host`). Если 404 везде — это
    настоящее «карточки нет». Любая другая ошибка (блок, 5xx) — как раньше, без перебора."""
    last_error: RequestError | None = None
    for host in get_wb_basket_host_candidates(nm_id):
        try:
            response = await ctx.request(
                'GET',
                get_wb_card_json_url(nm_id, host),
                extra_headers=build_wb_cdn_headers(ctx.session_message, product_url),
                retryable_status_codes=WB_RETRYABLE_STATUS_CODES,
                is_blocked=is_wb_blocked_response,
            )
        except RequestError as error:
            if error.status_code != 404:
                raise
            last_error = error
            continue
        remember_wb_basket_host(nm_id, host)
        return response.json()
    raise last_error


async def fetch_wb_product_page(
    product_url: str,
    cursor: None,
    ctx: FetchContext,
) -> Page[ProductPagePayload]:
    nm_id = extract_wb_nm_id_from_url(product_url)
    if nm_id is None:
        raise InputResolutionError(f'cannot extract nm_id from {product_url!r}')
    size_option_id = extract_wb_size_option_id_from_url(product_url)

    await ctx.request(
        'GET',
        product_url,
        extra_headers={
            **build_wb_navigation_headers(ctx.session_message),
            'referer': WB_BASE_URL + '/',
            'sec-fetch-site': 'same-origin',
        },
        retryable_status_codes=WB_RETRYABLE_STATUS_CODES,
        is_blocked=is_wb_blocked_response,
    )
    card_api_response = await ctx.request(
        'GET',
        WB_CARD_API,
        params={**WB_CARD_PARAMS, 'nm': str(nm_id)},
        extra_headers=build_wb_api_headers(ctx.session_message, product_url),
        retryable_status_codes=WB_RETRYABLE_STATUS_CODES,
        is_blocked=is_wb_blocked_response,
    )
    card_api_data = card_api_response.json()
    products = card_api_data.get('products') or []
    if not products:
        raise UpstreamDataError(f'card API returned no products for nm_id={nm_id}')
    card_api_product = products[0]

    card_data = await _fetch_wb_card_json(nm_id, product_url, ctx)

    return Page(
        items=[extract_wb_product_page(card_data, card_api_product, nm_id, size_option_id)],
    )


async def fetch_wb_seller_profile(
    seller_url: str,
    ctx: FetchContext,
) -> SellerProfilePayload:
    supplier_id = extract_wb_supplier_id_from_url(seller_url)
    if supplier_id is None:
        raise InputResolutionError(f'Cannot extract supplier_id from URL: {seller_url!r}')
    seller_page_url = f'{WB_BASE_URL}/seller/{supplier_id}'

    cdn_url = WB_SUPPLIER_CDN_URL.format(supplier_id=supplier_id)
    cdn_response = await ctx.request(
        'GET',
        cdn_url,
        extra_headers=build_wb_cdn_headers(ctx.session_message, seller_page_url),
        retryable_status_codes=WB_RETRYABLE_STATUS_CODES,
    )
    cdn_data = cdn_response.json()

    metrics_url = WB_SUPPLIER_METRICS_API.format(supplier_id=supplier_id)
    metrics_response = await ctx.request(
        'GET',
        metrics_url,
        params={'curr': 'RUB'},
        extra_headers={
            **build_wb_cdn_headers(ctx.session_message, seller_page_url), 'x-client-name': 'site',
        },
        retryable_status_codes=WB_RETRYABLE_STATUS_CODES,
    )
    metrics_data = metrics_response.json()

    filters_response = await ctx.request(
        'GET',
        WB_SELLER_FILTERS_API,
        params={**WB_SELLER_FILTERS_PARAMS_BASE, 'supplier': str(supplier_id)},
        extra_headers=build_wb_api_headers(ctx.session_message, seller_page_url),
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


async def _resolve_wb_review_source(
    product_url: str,
    ctx: FetchContext,
) -> tuple[int, str]:
    nm_id = extract_wb_nm_id_from_url(product_url)
    if nm_id is None:
        raise InputResolutionError(f'cannot extract nm_id from {product_url!r}')

    await _wb_warmup(ctx)
    await ctx.request(
        'GET',
        product_url,
        extra_headers={
            **build_wb_navigation_headers(ctx.session_message),
            'referer': WB_BASE_URL + '/',
            'sec-fetch-site': 'same-origin',
        },
        retryable_status_codes=WB_RETRYABLE_STATUS_CODES,
        is_blocked=is_wb_blocked_response,
    )

    card_response = await ctx.request(
        'GET',
        WB_CARD_API,
        params={**WB_CARD_PARAMS, 'nm': str(nm_id)},
        extra_headers=build_wb_api_headers(ctx.session_message, product_url),
        retryable_status_codes=WB_RETRYABLE_STATUS_CODES,
        is_blocked=is_wb_blocked_response,
    )
    products = card_response.json().get('products') or []
    if not products:
        raise UpstreamDataError(f'card API returned no products for nm_id={nm_id}')
    root_id = int(products[0]['root'])

    feedback_host_response = await ctx.request(
        'GET',
        WB_FEEDBACK_HOST_API,
        params={'imt': str(root_id)},
        extra_headers=build_wb_cdn_headers(ctx.session_message, product_url),
        retryable_status_codes=WB_RETRYABLE_STATUS_CODES,
        is_blocked=is_wb_blocked_response,
    )
    hosts: list[str] = feedback_host_response.json()
    if not hosts:
        raise UpstreamDataError(f'feedback host API returned empty list for root_id={root_id}')
    return root_id, hosts[0]


def _guard_reviews_payload(payload: dict) -> None:
    """Ответ без списка отзывов или пустой список при ненулевом `feedbackCount` — сбой сессии, а не
    «отзывов нет»: смена сессии и повтор. Товар без отзывов (`feedbackCount == 0`) — норма."""
    if 'feedbacks' not in payload or (payload.get('feedbackCount') and not payload['feedbacks']):
        raise SuspiciousThinResultError('degraded WB reviews response')


async def fetch_wb_review_page(
    product_url: str,
    cursor: WbReviewCursor | None,
    ctx: FetchContext,
) -> Page[ReviewPayload]:
    """WB отдаёт все отзывы товара одним ответом, поэтому «страница» — срез результата.
    `review_page_size=None` (режим задач) — все отзывы разом. Со страницей (direct) `root_id` и
    хост фидбеков едут в курсоре: первая страница платит за прогрев и их определение, следующие
    — один запрос."""
    if cursor is None:
        root_id, feedback_host = await _resolve_wb_review_source(product_url, ctx)
        offset = 0
    else:
        root_id, feedback_host, offset = cursor.root_id, cursor.feedback_host, cursor.offset

    feedback_response = await ctx.request(
        'GET',
        f'{feedback_host}/feedbacks/v2/{root_id}',
        extra_headers=build_wb_cdn_headers(ctx.session_message, product_url),
        retryable_status_codes=WB_RETRYABLE_STATUS_CODES,
        is_blocked=is_wb_blocked_response,
    )
    feedback_payload = feedback_response.json()
    _guard_reviews_payload(feedback_payload)
    reviews, _ = extract_wb_review_list(feedback_payload, set())

    if ctx.review_page_size is None:
        return Page(items=reviews)
    page_items = reviews[offset:offset + ctx.review_page_size]
    next_offset = offset + len(page_items)
    if not page_items or next_offset >= len(reviews):
        return Page(items=page_items)
    return Page(
        items=page_items,
        next_cursor=WbReviewCursor(
            marketplace=Marketplace.WILDBERRIES,
            offset=next_offset,
            root_id=root_id,
            feedback_host=feedback_host,
        ),
    )
