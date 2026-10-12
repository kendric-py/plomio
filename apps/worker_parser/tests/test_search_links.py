"""Поиск по ссылке с фильтрами: сайт передаёт параметры ссылки в API под теми же именами, воркер
берёт их из ссылки (см. `apps/worker_parser/AGENTS.md`, «Поиск по ссылке»)."""
from urllib.parse import parse_qsl, urlparse

import pytest

from apps.worker_parser.src.entities import OzonPaginationCursor, WildberriesPaginationCursor
from apps.worker_parser.src.exceptions import InputResolutionError
from apps.worker_parser.src.marketplaces.ozon.fetchers import fetch_ozon_search_page
from apps.worker_parser.src.marketplaces.ozon.utils import build_ozon_search_relative_url
from apps.worker_parser.src.marketplaces.wb.fetchers import fetch_wb_search_page
from apps.worker_parser.src.marketplaces.wb.utils import parse_wb_search_input
from core.enums import Marketplace
from fakes import FakeContext, make_session_message

WB_LINK = (
    'https://www.wildberries.ru/catalog/0/search.aspx?search=кроссовки&sort=priceup'
    '&priceU=100000;500000&fbrand=155&fcolor=0;1&fsize=44&page=3&dest=-1&appType=9'
)


def ozon_query(relative_url: str) -> list[tuple[str, str]]:
    return parse_qsl(urlparse(relative_url).query)


# --- WB ---


def wb_payload() -> dict:
    return {'products': [{'id': 1, 'name': 'n', 'sizes': []}], 'total': 1}


def test_wb_text_is_a_plain_query():
    assert parse_wb_search_input('  чехол iphone ') == ('чехол iphone', {})


def test_wb_link_gives_query_and_filters_without_service_params():
    query, filters = parse_wb_search_input(WB_LINK)
    assert query == 'кроссовки'
    assert filters == {
        'sort': 'priceup', 'priceU': '100000;500000', 'fbrand': '155', 'fcolor': '0;1',
        'fsize': '44',
    }


@pytest.mark.parametrize('link', [
    'https://evil.example/catalog/0/search.aspx?search=q',
    'https://www.wildberries.ru.evil.example/catalog/0/search.aspx?search=q',
    'https://www.wildberries.ru/catalog/0/search.aspx',
    'https://www.wildberries.ru/catalog/0/search.aspx?search=',
])
def test_wb_bad_link_is_invalid_input(link):
    with pytest.raises(InputResolutionError):
        parse_wb_search_input(link)


@pytest.mark.asyncio
async def test_wb_search_link_filters_go_to_api_params():
    context = FakeContext([wb_payload()], make_session_message())
    cursor = WildberriesPaginationCursor(marketplace=Marketplace.WILDBERRIES, page_num=0)
    await fetch_wb_search_page(WB_LINK, cursor, context)
    _, params = context.requests[-1]
    assert params['query'] == 'кроссовки'
    assert params['page'] == '1'
    assert params['priceU'] == '100000;500000'
    assert params['fbrand'] == '155'
    assert params['sort'] == 'priceup'
    assert params['inheritFilters'] == 'true'
    assert params['dest'] != '-1'


@pytest.mark.asyncio
async def test_wb_search_text_params_are_unchanged():
    context = FakeContext([wb_payload()], make_session_message())
    cursor = WildberriesPaginationCursor(marketplace=Marketplace.WILDBERRIES, page_num=0)
    await fetch_wb_search_page('q', cursor, context)
    _, params = context.requests[-1]
    assert params['query'] == 'q'
    assert params['inheritFilters'] == 'false'
    assert 'fbrand' not in params


# --- Ozon ---


def test_ozon_text_builds_plain_search_url():
    assert build_ozon_search_relative_url(' чехол ') == (
        '/search/?from_global=true&text=%D1%87%D0%B5%D1%85%D0%BE%D0%BB'
    )


def test_ozon_link_keeps_filters_and_drops_pagination_state():
    link = (
        'https://www.ozon.ru/search/?text=кроссовки&currency_price=1000.000%3B5000.000'
        '&sorting=price&page=2&paginator_token=1&search_page_state=abc&__rr=1'
    )
    relative = build_ozon_search_relative_url(link)
    assert relative.startswith('/search/?')
    assert sorted(ozon_query(relative)) == sorted([
        ('from_global', 'true'), ('text', 'кроссовки'),
        ('currency_price', '1000.000;5000.000'), ('sorting', 'price'),
    ])


@pytest.mark.parametrize('link', [
    'https://evil.example/search/?text=q',
    'https://www.ozon.ru.evil.example/search/?text=q',
    'https://www.ozon.ru/category/obuv-17777/?text=q',
    'https://www.ozon.ru/search/',
])
def test_ozon_bad_link_is_invalid_input(link):
    with pytest.raises(InputResolutionError):
        build_ozon_search_relative_url(link)


@pytest.mark.asyncio
async def test_ozon_search_link_first_request_carries_filters():
    payload = {'widgetStates': {}, 'pageInfo': {'url': '/search/'}}
    context = FakeContext([{}, payload], make_session_message())
    link = 'https://www.ozon.ru/search/?text=q&currency_price=1000.000%3B5000.000'
    await fetch_ozon_search_page(link, None, context)
    warmup_url, _ = context.requests[0]
    _, api_params = context.requests[1]
    assert 'currency_price=1000.000%3B5000.000' in warmup_url
    assert ('currency_price', '1000.000;5000.000') in ozon_query(api_params['url'])


@pytest.mark.asyncio
async def test_ozon_search_link_ignored_when_cursor_present():
    payload = {'widgetStates': {}, 'pageInfo': {'url': '/search/'}}
    context = FakeContext([payload], make_session_message())
    cursor = OzonPaginationCursor(
        marketplace=Marketplace.OZON, next_url='/search/?page=2', referer='https://www.ozon.ru/',
    )
    await fetch_ozon_search_page('https://evil.example/', cursor, context)
    assert context.requests[0][1]['url'] == '/search/?page=2'
