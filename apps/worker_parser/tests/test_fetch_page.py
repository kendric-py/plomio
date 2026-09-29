import json
import pytest

from apps.worker_parser.src.entities import OzonReviewCursor, SessionMessage, WbReviewCursor
from apps.worker_parser.src.marketplaces.ozon.fetchers import fetch_ozon_review_page
from apps.worker_parser.src.marketplaces.ozon.utils import extract_ozon_product_id_from_path
from apps.worker_parser.src.marketplaces.wb.fetchers import fetch_wb_review_page
from core.enums import Marketplace
from fakes import FakeContext, make_session_message


WB_URL = 'https://www.wildberries.ru/catalog/1/detail.aspx'


@pytest.fixture
def session_message() -> SessionMessage:
    return make_session_message()


@pytest.mark.parametrize('path, expected', [
    ('/product/naushniki-tour-pro-2-5059314345/', '5059314345'),
    ('/product/5059314345/', '5059314345'),
    ('/product/abc/', 'unknown'),
])
def test_extract_ozon_product_id(path, expected):
    assert extract_ozon_product_id_from_path(path) == expected


@pytest.mark.asyncio
async def test_ozon_reviews_single_request_and_cursor_from_next_button(
    load_fixture, session_message,
):
    context = FakeContext([load_fixture('ozon_reviews__3')], session_message)
    page = await fetch_ozon_review_page('https://www.ozon.ru/product/5059314345/', None, context)

    assert len(page.items) == 30
    assert len(context.requests) == 1
    assert context.requests[0][1] == {'url': '/product/5059314345/reviews/?sort=usefulness_desc'}
    assert page.next_cursor.next_params.startswith('?page=2&page_key=')
    assert page.next_cursor.seen_uuids == []


@pytest.mark.asyncio
async def test_ozon_reviews_follow_cursor_params(load_fixture, session_message):
    cursor = OzonReviewCursor(
        marketplace=Marketplace.OZON, sort_order='usefulness_desc',
        next_params='?page=2&page_key=k',
    )
    context = FakeContext([load_fixture('ozon_reviews__4')], session_message)
    await fetch_ozon_review_page('https://www.ozon.ru/product/5059314345/', cursor, context)

    assert context.requests[0][1] == {'url': '/product/5059314345/reviews/?page=2&page_key=k'}


def empty_reviews_payload() -> dict:
    widget = {'reviews': [], 'paging': {'nextButton': ''}}
    return {'widgetStates': {'webListReviews-1': json.dumps(widget)}}


@pytest.mark.asyncio
async def test_ozon_reviews_end_of_chain_without_sort_walk(session_message):
    context = FakeContext([empty_reviews_payload()], session_message)
    page = await fetch_ozon_review_page('https://www.ozon.ru/product/1/', None, context)
    assert page.next_cursor is None


@pytest.mark.asyncio
async def test_ozon_reviews_sort_walk_moves_to_next_sort(session_message):
    context = FakeContext([empty_reviews_payload()], session_message, walk_all_review_sorts=True)
    page = await fetch_ozon_review_page('https://www.ozon.ru/product/1/', None, context)
    assert page.next_cursor.sort_order == 'score_desc'
    assert page.next_cursor.next_params is None


@pytest.mark.asyncio
async def test_ozon_reviews_sort_walk_ends_after_last_sort(session_message):
    cursor = OzonReviewCursor(marketplace=Marketplace.OZON, sort_order='score_asc')
    context = FakeContext([empty_reviews_payload()], session_message, walk_all_review_sorts=True)
    page = await fetch_ozon_review_page('https://www.ozon.ru/product/1/', cursor, context)
    assert page.next_cursor is None


def wb_feedbacks(count: int) -> dict:
    return {
        'feedbackCount': count,
        'feedbacks': [
            {
                'id': f'id-{index}', 'text': 'x', 'productValuation': 5,
                'createdDate': '2025-01-01T00:00:00Z',
            }
            for index in range(count)
        ],
    }


@pytest.mark.asyncio
async def test_wb_reviews_all_at_once_without_page_size(session_message):
    cursor = WbReviewCursor(
        marketplace=Marketplace.WILDBERRIES, offset=0, root_id=1, feedback_host='https://host',
    )
    context = FakeContext([wb_feedbacks(5)], session_message)
    page = await fetch_wb_review_page(WB_URL, cursor, context)
    assert len(page.items) == 5
    assert page.next_cursor is None


@pytest.mark.asyncio
async def test_wb_reviews_slice_uses_cursor_with_single_request(session_message):
    cursor = WbReviewCursor(
        marketplace=Marketplace.WILDBERRIES, offset=2, root_id=7, feedback_host='https://host',
    )
    context = FakeContext([wb_feedbacks(5)], session_message, review_page_size=2)
    page = await fetch_wb_review_page(WB_URL, cursor, context)

    assert [review.external_uuid for review in page.items] == ['id-2', 'id-3']
    assert page.next_cursor.offset == 4
    assert page.next_cursor.root_id == 7
    assert context.requests == [('https://host/feedbacks/v2/7', None)]


@pytest.mark.asyncio
async def test_wb_reviews_last_slice_has_no_cursor(session_message):
    cursor = WbReviewCursor(
        marketplace=Marketplace.WILDBERRIES, offset=4, root_id=7, feedback_host='https://host',
    )
    context = FakeContext([wb_feedbacks(5)], session_message, review_page_size=2)
    page = await fetch_wb_review_page(WB_URL, cursor, context)
    assert len(page.items) == 1
    assert page.next_cursor is None
