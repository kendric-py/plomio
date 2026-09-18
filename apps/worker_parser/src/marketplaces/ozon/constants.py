from enum import Enum

OZON_BASE_URL = 'https://www.ozon.ru'
OZON_SEARCH_API = 'https://www.ozon.ru/api/entrypoint-api.bx/page/json/v2'
OZON_RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({408, 425, 429, 500, 502, 503, 504})
OZON_API_TIMEOUT: float = 15.0

OZON_FALLBACK_MANIFEST_VERSION = (
    'frontend-ozon-ru:eacafdc4207d05988b8721af3d8b33f1c205d0c3,'
    'search-render-api:a0eaad67467046d6f20c733080dc11799bb4694d,'
    'sf-render-api:9a22549dde40340cf9707b363fd804dd31775ce4,'
    'checkout-render-api:2d3cb2882c9479b6c1b9a298f43a453764dd154e,'
    'fav-render-api:9d3f1045703d16b2af09e0441efcfc9818d31001'
)


class OzonReviewSortOrder(str, Enum):
    PUBLISHED_AT_DESC = 'published_at_desc'
    SCORE_DESC = 'score_desc'
    SCORE_ASC = 'score_asc'
