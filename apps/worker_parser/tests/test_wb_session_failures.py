"""Сбои сессии WB на страницах выдач и отзывов: деградировавший ответ и первая пустая страница не
считаются концом — вызов повторяется на другой сессии (см. AGENTS.md, «Сбои сессии WB»)."""
import pytest

from apps.worker_parser.src.entities import Page, WbReviewCursor, WildberriesPaginationCursor
from apps.worker_parser.src.exceptions import EmptyPageUnconfirmedError, SuspiciousThinResultError
from apps.worker_parser.src.execution import ExecutionOptions, PageExecutor
from apps.worker_parser.src.marketplaces.wb.fetchers import (
    fetch_wb_category_page,
    fetch_wb_review_page,
    fetch_wb_search_page,
    fetch_wb_seller_page,
)
from core.enums import Marketplace
from packages.result.src.entities import ProductPayload
from fakes import FakeContext, make_session_message
from test_execution import FakeProvider

PRODUCT = ProductPayload(external_id='1', title='t', product_url='u')
DEGRADED = {
    'metadata': {'catalog_type': 'preset'}, 'state': 0, 'version': 2, 'params': {},
    'data': {'products': [{'id': 301392582, 'name': 'MacBook Pro 16'}]},
}
EMPTY = {'metadata': {}, 'products': [], 'total': 105263}
SELLER_URL = 'https://www.wildberries.ru/seller/92684'
CATEGORY_URL = 'https://www.wildberries.ru/catalog/a/b'
REVIEWS_URL = 'https://www.wildberries.ru/catalog/1/detail.aspx'


def cursor() -> WildberriesPaginationCursor:
    return WildberriesPaginationCursor(marketplace=Marketplace.WILDBERRIES, page_num=1)


def review_cursor() -> WbReviewCursor:
    return WbReviewCursor(
        marketplace=Marketplace.WILDBERRIES, offset=0, root_id=1, feedback_host='https://h',
    )


@pytest.fixture
def session_message():
    return make_session_message()


@pytest.fixture
def category_menu(monkeypatch):
    async def menu(http_session, session_message):
        return {'/catalog/a/b': 'menu_v3_1 query'}

    monkeypatch.setattr(
        'apps.worker_parser.src.marketplaces.wb.fetchers.load_wb_menu_search_queries', menu,
    )


async def call_search(payload, session_message, **options):
    context = FakeContext([payload], session_message, **options)
    return await fetch_wb_search_page('q', cursor(), context)


async def call_seller(payload, session_message, **options):
    context = FakeContext([payload], session_message, **options)
    return await fetch_wb_seller_page(SELLER_URL, cursor(), context)


async def call_category(payload, session_message, **options):
    context = FakeContext([payload], session_message, **options)
    return await fetch_wb_category_page(CATEGORY_URL, cursor(), context)


@pytest.mark.asyncio
async def test_degraded_response_is_a_session_failure_on_every_listing(
    session_message, category_menu,
):
    with pytest.raises(SuspiciousThinResultError):
        await call_search(DEGRADED, session_message)
    with pytest.raises(SuspiciousThinResultError):
        await call_seller(DEGRADED, session_message)
    with pytest.raises(SuspiciousThinResultError):
        await call_category(DEGRADED, session_message)


@pytest.mark.asyncio
async def test_first_empty_page_needs_confirmation_on_every_listing(
    session_message, category_menu,
):
    with pytest.raises(EmptyPageUnconfirmedError):
        await call_search(EMPTY, session_message)
    with pytest.raises(EmptyPageUnconfirmedError):
        await call_seller(EMPTY, session_message)
    with pytest.raises(EmptyPageUnconfirmedError):
        await call_category(EMPTY, session_message)


@pytest.mark.asyncio
async def test_confirmed_empty_page_is_the_end_on_every_listing(session_message, category_menu):
    pages = [
        await call_search(EMPTY, session_message, confirm_empty_page=True),
        await call_seller(EMPTY, session_message, confirm_empty_page=True),
        await call_category(EMPTY, session_message, confirm_empty_page=True),
    ]
    for page in pages:
        assert page.items == [] and page.next_cursor is None


@pytest.mark.asyncio
async def test_reviews_without_list_or_with_lost_list_are_a_session_failure(session_message):
    for payload in ({'feedbackCount': 5}, {'feedbackCount': 5, 'feedbacks': []}, {}):
        context = FakeContext([payload], session_message)
        with pytest.raises(SuspiciousThinResultError):
            await fetch_wb_review_page(REVIEWS_URL, review_cursor(), context)


@pytest.mark.asyncio
async def test_product_without_reviews_is_normal(session_message):
    context = FakeContext([{'feedbackCount': 0, 'feedbacks': []}], session_message)
    page = await fetch_wb_review_page(REVIEWS_URL, review_cursor(), context)
    assert page.items == [] and page.next_cursor is None


class EmptyUntilConfirmed:
    """Пусто на первой сессии и на второй — как настоящий потолок выдачи."""

    def __init__(self) -> None:
        self.flags = []

    async def __call__(self, context) -> Page:
        self.flags.append(context.confirm_empty_page)
        if not context.confirm_empty_page:
            raise EmptyPageUnconfirmedError('empty')
        return Page(items=[])


class EmptyThenFull:
    """Первая сессия пуста, вторая отдаёт данные — сбой сессии, а не конец."""

    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, context) -> Page:
        self.calls += 1
        if self.calls == 1:
            raise EmptyPageUnconfirmedError('empty')
        return Page(items=[PRODUCT])


class DegradedThenFull:
    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, context) -> Page:
        self.calls += 1
        if self.calls == 1:
            raise SuspiciousThinResultError('degraded')
        return Page(items=[PRODUCT])


@pytest.mark.asyncio
async def test_executor_confirms_empty_page_on_another_session():
    provider = FakeProvider()
    call = EmptyUntilConfirmed()
    page = await PageExecutor(provider, ExecutionOptions()).run(call)
    assert page.items == []
    assert call.flags == [False, True]
    assert provider.events == ['acquire', 'discard', 'acquire']


@pytest.mark.asyncio
async def test_executor_takes_data_when_another_session_has_it():
    executor = PageExecutor(FakeProvider(), ExecutionOptions(max_attempts=2))
    page = await executor.run(EmptyThenFull())
    assert page.items == [PRODUCT]


@pytest.mark.asyncio
async def test_degraded_response_is_retried_on_a_new_session():
    provider = FakeProvider()
    page = await PageExecutor(provider, ExecutionOptions()).run(DegradedThenFull())
    assert page.items == [PRODUCT]
    assert provider.events == ['acquire', 'discard', 'acquire']
