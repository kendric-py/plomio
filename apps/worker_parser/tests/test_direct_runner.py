import time
from dataclasses import dataclass, field

import pytest

from apps.worker_parser.src import direct_runner
from apps.worker_parser.src.entities import Page, WbReviewCursor
from apps.worker_parser.src.exceptions import InputResolutionError, RequestError
from apps.worker_parser.src.execution import ExecutionOptions, PageExecutor
from apps.worker_parser.src.registry import PageOperation
from apps.worker_parser.src.session_provider import SessionHandle
from core.enums import Marketplace
from packages.direct.src.entities import DirectRequest
from packages.direct.src.enums import DirectRequestType, DirectStatus
from packages.result.src.entities import ProductPayload
from packages.task.src.enums import ParseType


def make_request(
    request_type=DirectRequestType.PRODUCT_PAGE,
    marketplace=Marketplace.WILDBERRIES,
    input_value='123',
    page_cursor=None,
    deadline_in=20.0,
) -> DirectRequest:
    now = time.time()
    return DirectRequest(
        request_id='req-1',
        request_type=request_type,
        marketplace=marketplace,
        input_value=input_value,
        page_cursor=page_cursor,
        created_at=now,
        deadline_at=now + deadline_in,
    )


@pytest.mark.parametrize('marketplace, value, expected', [
    (Marketplace.WILDBERRIES, '123', 'https://www.wildberries.ru/catalog/123/detail.aspx'),
    (Marketplace.OZON, '123', 'https://www.ozon.ru/product/123/'),
    (Marketplace.OZON, 'https://www.ozon.ru/product/n-5/', 'https://www.ozon.ru/product/n-5/'),
    (Marketplace.OZON, ' 77 ', 'https://www.ozon.ru/product/77/'),
])
def test_resolve_article_to_url(marketplace, value, expected):
    request = make_request(marketplace=marketplace, input_value=value)
    assert direct_runner.resolve_input_value(request) == expected


@pytest.mark.parametrize('marketplace, value', [
    (Marketplace.WILDBERRIES, 'abc'),
    (Marketplace.OZON, 'not-a-link'),
    (Marketplace.OZON, 'https://www.ozon.ru/category/phones/'),
    (Marketplace.OZON, ''),
])
def test_resolve_rejects_non_article(marketplace, value):
    request = make_request(marketplace=marketplace, input_value=value)
    with pytest.raises(InputResolutionError):
        direct_runner.resolve_input_value(request)


def test_search_text_passed_as_is():
    request = make_request(DirectRequestType.SEARCH, input_value='  чехол iphone ')
    assert direct_runner.resolve_input_value(request) == 'чехол iphone'


def test_bad_cursor_shape_is_invalid_input():
    operation = PageOperation(fetch_page=None, cursor_model=WbReviewCursor)
    with pytest.raises(InputResolutionError):
        direct_runner.restore_cursor(operation, {'garbage': 1})


class StubProvider:
    async def acquire(self, deadline):
        return SessionHandle(session_message=None, http_session=None)

    async def release(self, handle):
        return None

    async def discard(self, handle):
        return None


@dataclass
class FakeBus:
    replies: list = field(default_factory=list)

    async def publish_reply(self, reply):
        self.replies.append(reply)


def install_operation(monkeypatch, parse_type, fetch_page, cursor_model=None):
    operation = PageOperation(fetch_page=fetch_page, cursor_model=cursor_model)
    monkeypatch.setitem(
        direct_runner.OPERATIONS, (Marketplace.WILDBERRIES, parse_type), operation,
    )


def make_executor() -> PageExecutor:
    return PageExecutor(StubProvider(), ExecutionOptions(max_attempts=2))


@pytest.mark.asyncio
async def test_search_reply_carries_items_and_raw_cursor(monkeypatch):
    async def fetch_page(input_value, cursor, ctx):
        product = ProductPayload(external_id='1', title='t', product_url='u')
        return Page(items=[product], next_cursor=WbReviewCursor(
            marketplace=Marketplace.WILDBERRIES, offset=1, root_id=2, feedback_host='h',
        ))

    install_operation(monkeypatch, ParseType.SEARCH_QUERY, fetch_page)
    request = make_request(DirectRequestType.SEARCH, input_value='q')

    reply = await direct_runner.execute_direct_request(request, make_executor())

    assert reply.status == DirectStatus.OK
    assert reply.payload['items'][0]['external_id'] == '1'
    assert reply.next_cursor['offset'] == 1


@pytest.mark.asyncio
async def test_input_error_maps_to_invalid_input_without_fetching(monkeypatch):
    called = []

    async def fetch_page(input_value, cursor, ctx):
        called.append(1)

    install_operation(monkeypatch, ParseType.PRODUCT_PAGE, fetch_page)
    reply = await direct_runner.execute_direct_request(
        make_request(input_value='abc'), make_executor(),
    )
    assert reply.status == DirectStatus.INVALID_INPUT
    assert called == []


@pytest.mark.asyncio
async def test_404_maps_to_not_found(monkeypatch):
    async def fetch_page(input_value, cursor, ctx):
        raise RequestError('missing', status_code=404)

    install_operation(monkeypatch, ParseType.PRODUCT_PAGE, fetch_page)
    reply = await direct_runner.execute_direct_request(make_request(), make_executor())
    assert reply.status == DirectStatus.NOT_FOUND


@pytest.mark.asyncio
async def test_other_parser_errors_map_to_error_after_attempts(monkeypatch):
    calls = []

    async def fetch_page(input_value, cursor, ctx):
        calls.append(1)
        raise RequestError('boom', status_code=500)

    install_operation(monkeypatch, ParseType.PRODUCT_PAGE, fetch_page)
    reply = await direct_runner.execute_direct_request(make_request(), make_executor())
    assert reply.status == DirectStatus.ERROR
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_unexpected_exception_becomes_internal_error_reply(monkeypatch):
    async def fetch_page(input_value, cursor, ctx):
        raise ZeroDivisionError

    install_operation(monkeypatch, ParseType.PRODUCT_PAGE, fetch_page)
    bus = FakeBus()
    slot = StubProvider()

    await direct_runner.handle_direct_request(make_request(), bus, slot)

    assert bus.replies[0].status == DirectStatus.ERROR
    assert bus.replies[0].error == 'internal error: ZeroDivisionError'


@pytest.mark.asyncio
async def test_expired_request_is_dropped_without_reply(monkeypatch):
    bus = FakeBus()
    await direct_runner.handle_direct_request(
        make_request(deadline_in=-1.0), bus, StubProvider(),
    )
    assert bus.replies == []


@pytest.mark.asyncio
async def test_empty_page_never_carries_next_cursor(monkeypatch):
    async def fetch_page(input_value, cursor, ctx):
        return Page(items=[], next_cursor=WbReviewCursor(
            marketplace=Marketplace.WILDBERRIES, offset=1, root_id=2, feedback_host='h',
        ))

    install_operation(monkeypatch, ParseType.SEARCH_QUERY, fetch_page)
    request = make_request(DirectRequestType.SEARCH, input_value='q')

    reply = await direct_runner.execute_direct_request(request, make_executor())

    assert reply.status == DirectStatus.OK
    assert reply.next_cursor is None


@pytest.mark.parametrize('request_type, marketplace, value', [
    (DirectRequestType.CATEGORY, Marketplace.WILDBERRIES,
     'https://www.wildberries.ru/catalog/obuv/muzhskaya/botinki-i-polubotinki'),
    (DirectRequestType.CATEGORY, Marketplace.OZON, 'https://www.ozon.ru/category/smartfony-15502/'),
    (DirectRequestType.SELLER, Marketplace.WILDBERRIES, 'https://www.wildberries.ru/seller/92684'),
    (DirectRequestType.SELLER, Marketplace.OZON, 'https://www.ozon.ru/seller/mvideo-7/'),
])
def test_marketplace_links_are_accepted(request_type, marketplace, value):
    request = make_request(request_type, marketplace, value)
    assert direct_runner.resolve_input_value(request) == value


@pytest.mark.parametrize('request_type', [
    DirectRequestType.CATEGORY, DirectRequestType.SELLER,
    DirectRequestType.PRODUCT_PAGE, DirectRequestType.REVIEWS,
])
@pytest.mark.parametrize('value', [
    'https://evil.example/catalog/1/', 'https://www.wildberries.ru.evil.example/catalog/1/',
    'http://169.254.169.254/latest', 'ftp://www.wildberries.ru/x', 'not-a-link',
])
def test_foreign_or_broken_links_are_rejected(request_type, value):
    """Воркер запрашивает ссылку своей сессией: чужой хост недопустим ни для одного типа."""
    request = make_request(request_type, Marketplace.WILDBERRIES, value)
    with pytest.raises(InputResolutionError):
        direct_runner.resolve_input_value(request)


def test_seller_id_becomes_a_link_only_for_wildberries():
    wb = make_request(DirectRequestType.SELLER, Marketplace.WILDBERRIES, '92684')
    assert direct_runner.resolve_input_value(wb) == 'https://www.wildberries.ru/seller/92684'
    ozon = make_request(DirectRequestType.SELLER, Marketplace.OZON, '92684')
    with pytest.raises(InputResolutionError):
        direct_runner.resolve_input_value(ozon)


def test_category_and_seller_map_to_parse_types():
    mapping = direct_runner.PARSE_TYPE_BY_REQUEST_TYPE
    assert mapping[DirectRequestType.CATEGORY] == ParseType.CATEGORY
    assert mapping[DirectRequestType.SELLER] == ParseType.SELLER
