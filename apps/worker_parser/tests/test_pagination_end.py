"""Определение конца пагинации по типам выдачи. Правила выведены из живых прогонов (см.
`apps/worker_parser/AGENTS.md`, «Конец выдачи»):

- WB-поиск: конец — ответ-ошибка WB на страницу больше лимита (60) или ответ без товаров;
  короткая страница и смена набора (`merger` → `preset`) концом не считаются.
- Ozon-поиск: конец — когда в ответе нет `nextPage`; пустая страница ссылку дальше отдаёт.
- Ozon-отзывы: конец — пустой `paging.nextButton` или страница без новых отзывов.
- WB-отзывы: срез дошёл до конца списка.
"""
import copy
import json

import pytest

from apps.worker_parser.src.entities import (
    OzonPaginationCursor,
    OzonReviewCursor,
    SessionMessage,
    WildberriesPaginationCursor,
)
from apps.worker_parser.src.exceptions import UpstreamDataError
from apps.worker_parser.src.marketplaces.ozon.fetchers import (
    fetch_ozon_review_page,
    fetch_ozon_search_page,
)
from apps.worker_parser.src.marketplaces.ozon.pagination import extract_ozon_next_page
from apps.worker_parser.src.marketplaces.wb.constants import WB_PAGE_SIZE
from apps.worker_parser.src.marketplaces.wb.fetchers import fetch_wb_search_page
from core.enums import Marketplace
from fakes import FakeContext, make_session_message

OZON_PRODUCT_URL = 'https://www.ozon.ru/product/5059314345/'


@pytest.fixture
def session_message() -> SessionMessage:
    return make_session_message()


def wb_search_payload(count: int, start_id: int = 1) -> dict:
    return {
        'products': [
            {'id': start_id + index, 'name': f'name-{index}', 'sizes': []}
            for index in range(count)
        ],
        'total': 121585,
    }


def wb_cursor() -> WildberriesPaginationCursor:
    return WildberriesPaginationCursor(marketplace=Marketplace.WILDBERRIES, page_num=1)


# --- WB, поиск ---


@pytest.mark.asyncio
async def test_wb_search_full_page_continues(session_message):
    context = FakeContext([wb_search_payload(WB_PAGE_SIZE)], session_message)
    page = await fetch_wb_search_page('q', wb_cursor(), context)
    assert page.next_cursor is not None and page.next_cursor.page_num == 2


@pytest.mark.asyncio
async def test_wb_search_short_page_is_not_the_end(session_message):
    """Короткая страница конец не означает (её же даёт деградировавший ответ) — конец задают
    ответ-ошибка WB или переход к подмешанному набору."""
    context = FakeContext([wb_search_payload(18)], session_message)
    page = await fetch_wb_search_page('q', wb_cursor(), context)
    assert len(page.items) == 18
    assert page.next_cursor is not None and page.next_cursor.page_num == 2


@pytest.mark.asyncio
async def test_wb_search_page_limit_error_is_the_end(session_message):
    payload = {'error': 'binding request: page param malformed', 'code': 500}
    context = FakeContext([payload], session_message)
    page = await fetch_wb_search_page('q', wb_cursor(), context)
    assert page.items == [] and page.next_cursor is None


@pytest.mark.asyncio
async def test_wb_search_unknown_error_is_a_failure_not_an_end(session_message):
    context = FakeContext([{'error': 'something else', 'code': 500}], session_message)
    with pytest.raises(UpstreamDataError):
        await fetch_wb_search_page('q', wb_cursor(), context)


@pytest.mark.asyncio
async def test_wb_search_preset_page_is_kept(session_message):
    """Подмешанный WB набор (`preset`) не отбрасывается и конца выдачи не означает."""
    payload = {**wb_search_payload(WB_PAGE_SIZE), 'metadata': {'catalog_type': 'preset'}}
    context = FakeContext([payload], session_message)
    page = await fetch_wb_search_page('q', wb_cursor(), context)
    assert len(page.items) == WB_PAGE_SIZE and page.next_cursor is not None


@pytest.mark.asyncio
async def test_wb_search_no_results_shape_is_the_end(session_message):
    """Форма «ничего не найдено» (запрос `rc8090`): без `products` и `total`."""
    payload = {'name': 'rc8090', 'query': 'q', 'shardKey': 'merger', 'search_result': {}}
    context = FakeContext([payload], session_message)
    page = await fetch_wb_search_page('q', wb_cursor(), context)
    assert page.items == [] and page.next_cursor is None


@pytest.mark.asyncio
async def test_wb_search_confirmed_empty_page_is_the_end(session_message):
    context = FakeContext(
        [{'products': [], 'total': 0}], session_message, confirm_empty_page=True,
    )
    page = await fetch_wb_search_page('q', wb_cursor(), context)
    assert page.items == [] and page.next_cursor is None


@pytest.mark.asyncio
async def test_wb_search_dedup_does_not_end_pagination(session_message):
    """Живой прогон: страницы по 99 товаров после дедупликации — при полной сырой странице
    выдача не закончена (иначе теряли бы хвост)."""
    seen = {str(index) for index in range(1, 6)}
    context = FakeContext([wb_search_payload(WB_PAGE_SIZE)], session_message, seen_keys=seen)
    page = await fetch_wb_search_page('q', wb_cursor(), context)
    assert len(page.items) == WB_PAGE_SIZE - 5
    assert page.next_cursor is not None


@pytest.mark.asyncio
async def test_wb_search_limit_reached_is_the_end(session_message):
    context = FakeContext([wb_search_payload(WB_PAGE_SIZE)], session_message, limit=10)
    page = await fetch_wb_search_page('q', wb_cursor(), context)
    assert len(page.items) == 10 and page.next_cursor is None


# --- Ozon, поиск ---


def ozon_cursor() -> OzonPaginationCursor:
    return OzonPaginationCursor(
        marketplace=Marketplace.OZON, next_url='/search/?text=q', referer='https://www.ozon.ru/',
    )


@pytest.mark.asyncio
async def test_ozon_search_next_page_present_continues(load_fixture, session_message):
    payload = load_fixture('ozon_search__0')
    context = FakeContext([payload], session_message)
    page = await fetch_ozon_search_page('q', ozon_cursor(), context)
    assert page.items
    assert extract_ozon_next_page(payload) is not None
    assert page.next_cursor is not None


@pytest.mark.asyncio
async def test_ozon_search_without_next_page_is_the_end(load_fixture, session_message):
    payload = copy.deepcopy(load_fixture('ozon_search__0'))
    payload.pop('nextPage', None)
    for key, raw in list(payload.get('widgetStates', {}).items()):
        if 'aginator' in key:
            payload['widgetStates'][key] = json.dumps({})
    context = FakeContext([payload], session_message)
    page = await fetch_ozon_search_page('q', ozon_cursor(), context)
    assert page.items and page.next_cursor is None


@pytest.mark.asyncio
async def test_ozon_search_empty_page_may_still_carry_next_cursor(session_message):
    """Живой прогон: редкий запрос — 2 пустые страницы, ссылка дальше есть. Фетчер отдаёт её как
    есть; конец для клиента direct определяет `build_ok_reply` (пустая страница = конец)."""
    payload = {'widgetStates': {}, 'nextPage': '/search/?page=2', 'pageInfo': {'url': '/search/'}}
    context = FakeContext([payload], session_message)
    page = await fetch_ozon_search_page('q', ozon_cursor(), context)
    assert page.items == [] and page.next_cursor is not None


# --- Ozon, отзывы ---


def reviews_payload(count: int, next_button: str) -> dict:
    widget = {
        'reviews': [
            {'uuid': f'u-{index}', 'content': {'score': 5}, 'author': {}, 'publishedAt': 1}
            for index in range(count)
        ],
        'paging': {'nextButton': next_button, 'total': 3368},
    }
    return {'widgetStates': {'webListReviews-1': json.dumps(widget)}}


@pytest.mark.asyncio
async def test_ozon_reviews_next_button_continues(session_message):
    context = FakeContext([reviews_payload(30, '?page=2&page_key=k')], session_message)
    page = await fetch_ozon_review_page(OZON_PRODUCT_URL, None, context)
    assert page.next_cursor.next_params == '?page=2&page_key=k'


@pytest.mark.asyncio
async def test_ozon_reviews_short_last_page_is_the_end(session_message):
    """Живой прогон: 86 отзывов — страницы 30, 30, 26 и `nextButton` пустой на последней."""
    context = FakeContext([reviews_payload(26, '')], session_message)
    page = await fetch_ozon_review_page(OZON_PRODUCT_URL, None, context)
    assert len(page.items) == 26 and page.next_cursor is None


@pytest.mark.asyncio
async def test_ozon_reviews_empty_trailing_page_is_the_end(session_message):
    """Живой прогон: у товара с потолком Ozon последняя страница пустая (30, ..., 30, 0)."""
    cursor = OzonReviewCursor(
        marketplace=Marketplace.OZON, sort_order='usefulness_desc', next_params='?page=34',
    )
    context = FakeContext([reviews_payload(0, '?page=35')], session_message)
    page = await fetch_ozon_review_page(OZON_PRODUCT_URL, cursor, context)
    assert page.items == [] and page.next_cursor is None


@pytest.mark.asyncio
async def test_ozon_reviews_sort_walk_ends_only_after_last_sort(session_message):
    """Режим задач: конец цепочки одной сортировки — переход к следующей, не конец выдачи."""
    context = FakeContext(
        [reviews_payload(0, '')], session_message, walk_all_review_sorts=True,
    )
    page = await fetch_ozon_review_page(OZON_PRODUCT_URL, None, context)
    assert page.next_cursor is not None and page.next_cursor.sort_order == 'score_desc'
