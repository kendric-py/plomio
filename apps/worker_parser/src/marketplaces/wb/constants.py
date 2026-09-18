from typing import Any

WB_BASE_URL = 'https://www.wildberries.ru'
WB_SEARCH_API = 'https://www.wildberries.ru/__internal/u-search/exactmatch/ru/common/v18/search'
WB_CARD_API = 'https://www.wildberries.ru/__internal/u-card/cards/v4/detail'
WB_SELLER_API = 'https://www.wildberries.ru/__internal/u-catalog/sellers/v4/catalog'
WB_FEEDBACK_HOST_API = 'https://feedback-bt.wildberries.ru/feedback/api/v2/host'
WB_MAIN_MENU_URL = 'https://static-basket-01.wbbasket.ru/vol0/data/main-menu-ru-ru-v3.json'
WB_SUPPLIER_CDN_URL = (
    'https://static-basket-01.wbbasket.ru/vol0/data/supplier-by-id/{supplier_id}.json'
)
WB_SUPPLIER_METRICS_API = (
    'https://suppliers-shipment-2.wildberries.ru/api/v1/suppliers/{supplier_id}'
)
WB_SELLER_FILTERS_API = 'https://www.wildberries.ru/__internal/u-catalog/sellers/v8/filters'

WB_RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({408, 425, 429, 500, 502, 503, 504})
WB_PAGE_SIZE = 100

WB_SEARCH_PARAMS_BASE: dict[str, Any] = {
    'ab_testing': 'false',
    'appType': '1',
    'curr': 'rub',
    'dest': '-1257786',
    'hide_dtype': '15',
    'hide_vflags': '4294967296',
    'inheritFilters': 'false',
    'lang': 'ru',
    'locale': 'ru',
    'resultset': 'catalog',
    'sort': 'popular',
    'spp': '30',
    'suppressSpellcheck': 'false',
}

WB_CATEGORY_PARAMS_BASE: dict[str, Any] = {
    'ab_testing': 'false',
    'appType': '1',
    'curr': 'rub',
    'dest': '-1257786',
    'hide_dtype': '15',
    'hide_vflags': '4294967296',
    'lang': 'ru',
    'locale': 'ru',
    'resultset': 'catalog',
    'sort': 'popular',
    'spp': '30',
    'suppressSpellcheck': 'false',
}

WB_CARD_PARAMS: dict[str, Any] = {
    'appType': '1',
    'curr': 'rub',
    'dest': '-1257786',
    'spp': '30',
    'hide_vflags': '4294967296',
    'hide_dtype': '15',
    'lang': 'ru',
    'ab_testing': 'false',
}

WB_SELLER_PARAMS_BASE: dict[str, Any] = {
    'ab_testing': 'false',
    'appType': '1',
    'curr': 'rub',
    'dest': '-1257786',
    'hide_dtype': '15',
    'hide_vflags': '4294967296',
    'lang': 'ru',
    'sort': 'popular',
    'spp': '30',
}

WB_SELLER_FILTERS_PARAMS_BASE: dict[str, Any] = {
    'ab_testing': 'false',
    'appType': '1',
    'curr': 'rub',
    'dest': '-1257786',
    'hide_dtype': '15',
    'hide_vflags': '4294967296',
    'lang': 'ru',
    'spp': '30',
}

WB_BASKET_RANGES: list[tuple[int, int, str]] = [
    (0, 143, 'basket-01.wbbasket.ru'),
    (144, 287, 'basket-02.wbbasket.ru'),
    (288, 431, 'basket-03.wbbasket.ru'),
    (432, 719, 'basket-04.wbbasket.ru'),
    (720, 1007, 'basket-05.wbbasket.ru'),
    (1008, 1061, 'basket-06.wbbasket.ru'),
    (1062, 1115, 'basket-07.wbbasket.ru'),
    (1116, 1169, 'basket-08.wbbasket.ru'),
    (1170, 1313, 'basket-09.wbbasket.ru'),
    (1314, 1601, 'basket-10.wbbasket.ru'),
    (1602, 1655, 'basket-11.wbbasket.ru'),
    (1656, 1919, 'basket-12.wbbasket.ru'),
    (1920, 2045, 'basket-13.wbbasket.ru'),
    (2046, 2189, 'basket-14.wbbasket.ru'),
    (2190, 2405, 'basket-15.wbbasket.ru'),
    (2406, 2621, 'basket-16.wbbasket.ru'),
    (2622, 2837, 'basket-17.wbbasket.ru'),
    (2838, 3053, 'basket-18.wbbasket.ru'),
    (3054, 3269, 'basket-19.wbbasket.ru'),
    (3270, 3485, 'basket-20.wbbasket.ru'),
    (3486, 3701, 'basket-21.wbbasket.ru'),
    (3702, 3917, 'basket-22.wbbasket.ru'),
    (3918, 4133, 'basket-23.wbbasket.ru'),
    (4134, 4349, 'basket-24.wbbasket.ru'),
    (4350, 4565, 'basket-25.wbbasket.ru'),
    (4566, 4877, 'basket-26.wbbasket.ru'),
    (4878, 5189, 'basket-27.wbbasket.ru'),
    (5190, 5501, 'basket-28.wbbasket.ru'),
    (5502, 5813, 'basket-29.wbbasket.ru'),
    (5814, 6125, 'basket-30.wbbasket.ru'),
    (6126, 6437, 'basket-31.wbbasket.ru'),
    (6438, 6749, 'basket-32.wbbasket.ru'),
    (6750, 7061, 'basket-33.wbbasket.ru'),
    (7062, 7373, 'basket-34.wbbasket.ru'),
    (7374, 7685, 'basket-35.wbbasket.ru'),
    (7686, 7997, 'basket-36.wbbasket.ru'),
    (7998, 8309, 'basket-37.wbbasket.ru'),
    (8310, 8741, 'basket-38.wbbasket.ru'),
    (8742, 9173, 'basket-39.wbbasket.ru'),
    (9174, 9605, 'basket-40.wbbasket.ru'),
    (9606, 10373, 'basket-41.wbbasket.ru'),
    (10374, 11141, 'basket-42.wbbasket.ru'),
    (11142, 11909, 'basket-43.wbbasket.ru'),
    (11910, 12677, 'basket-44.wbbasket.ru'),
    (12678, 13445, 'basket-45.wbbasket.ru'),
    (13446, 14213, 'basket-46.wbbasket.ru'),
]
