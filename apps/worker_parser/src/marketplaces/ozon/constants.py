OZON_BASE_URL = 'https://www.ozon.ru'
OZON_SEARCH_API = 'https://www.ozon.ru/api/entrypoint-api.bx/page/json/v2'
OZON_RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({408, 425, 429, 500, 502, 503, 504})
OZON_API_TIMEOUT: float = 15.0

# Snapshot of the real `x-o3-manifest-version` captured from live traffic on 2026-09-23 — kept
# in sync with the same constant in `apps/worker_sessions` (see that file for why this can't be
# derived per-session cheaply). Was previously stale and, worse, a different build entirely
# from the worker_sessions copy — the two had drifted independently.
OZON_FALLBACK_MANIFEST_VERSION = (
    'frontend-ozon-ru:a3eb349144e383363827d27cc22b89c6746e814a,'
    'checkout-render-api:658d7a993e214f39d71ac50969a4593a3a8e0189,'
    'search-render-api:48310d03704f2c4ffd36266a1be54936ef221aba,'
    'fav-render-api:4feb07757cd271fa29fd5ef84b68219b65c24228,'
    'sf-render-api:7613b842f83d7af57356f082f046a60c290a4a38,'
    'rtb-render-api:79a3ea34b45d993c7c29e094b0cb026d8e502ba7'
)


# Сортировки, реально применяемые Ozon на `{product}/reviews/`; `published_at_desc` Ozon молча
# заменяет на `usefulness_desc` (проверено на живых ответах), поэтому его здесь нет. Первая — по
# умолчанию, остальные — для обхода потолка страниц на одну сортировку.
OZON_REVIEW_SORT_ORDERS: tuple[str, ...] = ('usefulness_desc', 'score_desc', 'score_asc')
OZON_LISTING_HTTP_RETRIES = 2
OZON_LISTING_BASE_DELAY = 0.5
