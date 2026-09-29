import json

from apps.worker_parser.src.marketplaces.ozon.parsers import (
    extract_ozon_product_list,
    extract_ozon_product_page,
    extract_ozon_review_list,
)
from apps.worker_parser.src.marketplaces.wb.parsers import (
    extract_wb_product_list,
    extract_wb_product_page,
    extract_wb_review_list,
)

OZON_PRODUCT_PATH = '/product/naushniki-besprovodnye-s-mikrofonom-tour-pro-2-5059314345/'


def test_ozon_search_products(load_fixture):
    products = extract_ozon_product_list(load_fixture('ozon_search__0'), None, set())
    assert products
    assert all(product.title and product.product_url for product in products)


def test_ozon_product_page(load_fixture):
    page = extract_ozon_product_page(
        load_fixture('ozon_product__1'),
        load_fixture('ozon_product__2'),
        'https://www.ozon.ru' + OZON_PRODUCT_PATH,
        '5059314345',
    )
    assert page.external_id == '5059314345'
    assert page.title


def test_ozon_reviews_page_size_and_next_button(load_fixture):
    payload = load_fixture('ozon_reviews__3')
    reviews, total = extract_ozon_review_list(payload, set())
    assert len(reviews) == 30
    assert total > 30
    widget = next(
        json.loads(raw)
        for key, raw in payload['widgetStates'].items()
        if 'webListReviews' in key
    )
    assert widget['paging']['nextButton']


def test_ozon_reviews_pages_do_not_overlap(load_fixture):
    seen: set[str] = set()
    first, _ = extract_ozon_review_list(load_fixture('ozon_reviews__3'), seen)
    second, _ = extract_ozon_review_list(load_fixture('ozon_reviews__4'), seen)
    assert len(first) == len(second) == 30


def test_wb_search_products(load_fixture):
    products = extract_wb_product_list(load_fixture('wb_search__0'), None, set())
    assert products
    assert all(product.external_id for product in products)


def test_wb_product_page(load_fixture):
    card_api_product = load_fixture('wb_product__1')['products'][0]
    page = extract_wb_product_page(
        load_fixture('wb_product__2'), card_api_product, card_api_product['id'], None,
    )
    assert page.external_id == str(card_api_product['id'])
    assert page.title


def test_wb_reviews(load_fixture):
    reviews, _ = extract_wb_review_list(load_fixture('wb_reviews__5'), set())
    assert reviews
