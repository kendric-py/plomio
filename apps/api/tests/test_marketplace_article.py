import pytest

from core.enums import Marketplace
from core.marketplace_article import extract_article, normalize_product_input


@pytest.mark.parametrize(
    ('marketplace', 'value', 'expected'),
    [
        (Marketplace.OZON, '5314731595', 'https://www.ozon.ru/product/5314731595/'),
        (Marketplace.OZON, ' 5314731595 ', 'https://www.ozon.ru/product/5314731595/'),
        (
            Marketplace.WILDBERRIES, '123456',
            'https://www.wildberries.ru/catalog/123456/detail.aspx',
        ),
    ],
)
def test_bare_article_becomes_product_url(marketplace, value, expected):
    assert normalize_product_input(marketplace, value) == expected


@pytest.mark.parametrize(
    'value',
    ['https://www.ozon.ru/product/slug-5314731595/', 'not an article', ''],
)
def test_non_article_input_is_returned_as_is(value):
    assert normalize_product_input(Marketplace.OZON, value) == value


def test_article_survives_normalization():
    # Дубли ищутся по артикулу: из сохранённой (нормализованной) ссылки извлекается тот же.
    for marketplace in Marketplace:
        url = normalize_product_input(marketplace, '5314731595')
        assert extract_article(marketplace, url) == '5314731595'


def test_ozon_slug_link_article():
    assert extract_article(Marketplace.OZON, 'https://www.ozon.ru/product/slug-42/?x=1') == '42'
