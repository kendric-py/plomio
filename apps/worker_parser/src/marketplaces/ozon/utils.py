import re
from urllib.parse import urlparse

from curl_cffi.requests import AsyncSession

from apps.worker_parser.src.entities import SessionMessage


def extract_ozon_product_path_from_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed.path.rstrip('/') + '/'


def extract_ozon_product_id_from_path(path: str) -> str:
    match = re.search(r'-(\d+)/?$', path)
    return match.group(1) if match else 'unknown'


def is_ozon_blocked_response(status: int, content_type: str, body_prefix: str) -> bool:
    if status in {401, 403}:
        return True
    if status == 200 and content_type.startswith('application/json'):
        return False
    markers = ('__rr=1', 'abt-challenge', 'incidentid', 'captcha', '"error":"forbidden"')
    return any(marker in body_prefix for marker in markers)


def create_ozon_http_session(session_message: SessionMessage) -> AsyncSession:
    kwargs: dict = {'impersonate': 'chrome136'}
    if session_message.proxy:
        proxy_url = session_message.proxy.to_url()
        kwargs['proxies'] = {'http': proxy_url, 'https': proxy_url}
    http_session = AsyncSession(**kwargs)
    for name, value in session_message.cookies.items():
        http_session.cookies.set(name, value, domain='www.ozon.ru')
    http_session.cookies.set('xcid', session_message.extra['xcid'], domain='www.ozon.ru')
    http_session.cookies.set(
        '__Secure-ab-group', session_message.extra['ab_group'], domain='www.ozon.ru',
    )
    return http_session
