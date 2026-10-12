import re
from urllib.parse import parse_qsl, quote_plus, urlencode, urlparse

from curl_cffi.requests import AsyncSession

from apps.worker_parser.src.entities import SessionMessage
from apps.worker_parser.src.exceptions import InputResolutionError
from apps.worker_parser.src.marketplaces.ozon.constants import (
    OZON_HOSTS,
    OZON_SEARCH_LINK_IGNORED_PARAMS,
)


def build_ozon_search_relative_url(value: str) -> str:
    """Вход поиска → относительный URL выдачи для `entrypoint-api`. Текст без `http(s)://` —
    обычный поиск по тексту; иначе это ссылка на поиск Ozon (`/search/?text=...`): её параметры
    (фильтры, сортировка) сохраняются, кроме пагинации и состояния страницы
    (`OZON_SEARCH_LINK_IGNORED_PARAMS`). Чужой хост или ссылка не на поиск — `InputResolutionError`:
    ссылка запрашивается сессией с куками Ozon."""
    value = value.strip()
    if not value.lower().startswith(('http://', 'https://')):
        return f'/search/?from_global=true&text={quote_plus(value)}'
    parsed = urlparse(value)
    if parsed.hostname not in OZON_HOSTS:
        raise InputResolutionError(f'not an ozon link: {value[:80]!r}')
    if parsed.path.rstrip('/') != '/search':
        raise InputResolutionError('ozon search link must point to /search/')
    params = [
        (key, param_value)
        for key, param_value in parse_qsl(parsed.query, keep_blank_values=False)
        if key not in OZON_SEARCH_LINK_IGNORED_PARAMS
    ]
    if not any(key == 'text' and param_value.strip() for key, param_value in params):
        raise InputResolutionError('ozon search link has no `text` parameter')
    if not any(key == 'from_global' for key, _ in params):
        params.insert(0, ('from_global', 'true'))
    return '/search/?' + urlencode(params)


def extract_ozon_product_path_from_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed.path.rstrip('/') + '/'


def extract_ozon_product_id_from_path(path: str) -> str:
    match = re.search(r'(?:-|/product/)(\d+)/?$', path)
    return match.group(1) if match else 'unknown'


def is_ozon_blocked_response(status: int, content_type: str, body_prefix: str) -> bool:
    if status in {401, 403}:
        return True
    if status == 200 and content_type.startswith('application/json'):
        return False
    markers = ('__rr=1', 'abt-challenge', 'incidentid', 'captcha', '"error":"forbidden"')
    return any(marker in body_prefix for marker in markers)


def create_ozon_http_session(session_message: SessionMessage) -> AsyncSession:
    # Camoufox is a Firefox-engine browser — `session_message.user_agent` is a real Firefox
    # string. Impersonating Chrome's TLS/HTTP2 fingerprint here would contradict that
    # user-agent, a mismatch antibot can fingerprint on (see `build_ozon_navigation_headers`).
    kwargs: dict = {'impersonate': session_message.extra.get('impersonate', 'firefox135')}
    if session_message.proxy:
        proxy_url = session_message.proxy.to_curl_url()
        kwargs['proxies'] = {'http': proxy_url, 'https': proxy_url}
    http_session = AsyncSession(**kwargs)
    for name, value in session_message.cookies.items():
        http_session.cookies.set(name, value, domain='www.ozon.ru')
    http_session.cookies.set('xcid', session_message.extra['xcid'], domain='www.ozon.ru')
    http_session.cookies.set(
        '__Secure-ab-group', session_message.extra['ab_group'], domain='www.ozon.ru',
    )
    return http_session
