import logging
import uuid
from typing import Callable
from urllib.parse import quote_plus

from curl_cffi.requests import Session

from apps.worker_sessions.src.config import config
from apps.worker_sessions.src.entities import SessionMessage
from apps.worker_sessions.src.generation.marketplaces.ozon.constants import (
    OZON_BASE_URL,
    OZON_FALLBACK_MANIFEST_VERSION,
    OZON_SEARCH_API,
    OZON_VALIDATION_QUERY,
)
from apps.worker_sessions.src.generation.marketplaces.ozon.utils import is_ozon_blocked_response
from apps.worker_sessions.src.generation.marketplaces.wb.constants import (
    WB_BASE_URL,
    WB_SEARCH_API,
    WB_VALIDATION_PARAMS_BASE,
    WB_VALIDATION_QUERY,
)
from apps.worker_sessions.src.generation.marketplaces.wb.utils import is_wb_blocked_response
from core.enums import Marketplace

logger = logging.getLogger(__name__)


def _curl_proxy_url(session_message: SessionMessage) -> str | None:
    """curl_cffi/libcurl resolves DNS locally for a `socks5://` proxy URL, then hands the
    proxy a bare IP — the proxy network often can't route to that IP even though it can
    reach the hostname itself, surfacing as "SOCKS5 ... network unreachable". `socks5h://`
    makes libcurl forward the hostname and resolve through the proxy instead, matching how
    the browser side already behaves (its local SOCKS5 tunnel relays the hostname as-is)."""
    if session_message.proxy is None:
        return None
    url = session_message.proxy.to_url()
    if url.startswith('socks5://'):
        return 'socks5h://' + url.removeprefix('socks5://')
    return url


def _build_curl_session(
    session_message: SessionMessage,
    cookie_domain: str,
    extra_cookies: dict[str, str],
    impersonate: str = 'chrome136',
) -> Session:
    proxy_url = _curl_proxy_url(session_message=session_message)
    proxies = {'http': proxy_url, 'https': proxy_url} if proxy_url else None
    session = Session(impersonate=impersonate, proxies=proxies)
    for name, value in {**session_message.cookies, **extra_cookies}.items():
        session.cookies.set(name, value, domain=cookie_domain)
    return session


def _validate_wb(session_message: SessionMessage) -> bool:
    """Replays the same request sequence WB's search fetcher makes (homepage warmup, then the
    real search API with real params) — catches sessions that get blocked on the API even
    though they'd pass a homepage-only check."""
    # Camoufox is a Firefox-engine browser — the session's user-agent is a real Firefox
    # string (Camoufox doesn't spoof navigator.userAgent itself). Impersonating Chrome's
    # TLS/HTTP2 fingerprint and sending Chrome-only Client Hints headers here would
    # contradict that user-agent, a mismatch WB's antibot can fingerprint on.
    session = _build_curl_session(
        session_message=session_message,
        cookie_domain='www.wildberries.ru',
        extra_cookies={'deviceid': session_message.extra['device_id']},
        impersonate='firefox135',
    )
    nav_headers = {
        'accept': (
            'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8'
        ),
        'accept-language': 'ru-RU,ru;q=0.9,en;q=0.8',
        'sec-fetch-dest': 'document',
        'sec-fetch-mode': 'navigate',
        'upgrade-insecure-requests': '1',
        'user-agent': session_message.user_agent,
    }
    api_headers = {
        'accept': '*/*',
        'accept-language': 'ru-RU,ru;q=0.9,en;q=0.8',
        'deviceid': session_message.extra['device_id'],
        'referer': WB_BASE_URL + '/',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': session_message.user_agent,
        'x-requested-with': 'XMLHttpRequest',
        'x-spa-version': session_message.extra['spa_version'],
        'x-userid': '0',
    }
    if session_message.sec_ch_ua:
        for headers in (nav_headers, api_headers):
            headers['sec-ch-ua'] = session_message.sec_ch_ua
            headers['sec-ch-ua-mobile'] = '?0'
            headers['sec-ch-ua-platform'] = f'"{session_message.sec_ch_ua_platform}"'
    timeout = config.GENERATION.VALIDATION_TIMEOUT_SECONDS

    try:
        session.get(
            url=WB_BASE_URL + '/',
            headers={**nav_headers, 'sec-fetch-site': 'none'},
            timeout=timeout,
        )
        response = session.get(
            url=WB_SEARCH_API,
            params={**WB_VALIDATION_PARAMS_BASE, 'query': WB_VALIDATION_QUERY, 'page': '1'},
            headers=api_headers,
            timeout=timeout,
        )
    except Exception as exc:
        logger.warning('[validation_failed] marketplace=wildberries error=%s', exc)
        return False

    content_type = response.headers.get('content-type', '')
    body_prefix = response.text[:2000].lower()
    is_blocked = is_wb_blocked_response(
        status=response.status_code, content_type=content_type, body_prefix=body_prefix,
    )
    if is_blocked:
        logger.warning(
            '[validation_blocked] marketplace=wildberries status=%d', response.status_code,
        )
        return False
    logger.info('[validation_passed] marketplace=wildberries status=%d', response.status_code)
    return True


def _validate_ozon(session_message: SessionMessage) -> bool:
    """Replays the same request sequence Ozon's search fetcher makes (search-page navigation
    warmup, then the real entrypoint-api search) — catches sessions that get blocked on the
    API even though they'd pass a homepage-only check."""
    session = _build_curl_session(
        session_message=session_message,
        cookie_domain='www.ozon.ru',
        extra_cookies={
            'xcid': session_message.extra['xcid'],
            '__Secure-ab-group': session_message.extra['ab_group'],
        },
    )
    search_query = quote_plus(OZON_VALIDATION_QUERY)
    search_nav_url = f'{OZON_BASE_URL}/search/?from_global=true&text={search_query}'
    nav_headers = {
        'accept': (
            'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8'
        ),
        'accept-language': 'ru-RU,ru;q=0.9,en;q=0.8',
        'sec-ch-ua': session_message.sec_ch_ua,
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': f'"{session_message.sec_ch_ua_platform}"',
        'sec-fetch-dest': 'document',
        'sec-fetch-mode': 'navigate',
        'upgrade-insecure-requests': '1',
        'user-agent': session_message.user_agent,
        'referer': OZON_BASE_URL + '/',
        'sec-fetch-site': 'same-origin',
    }
    api_headers = {
        'accept': 'application/json',
        'accept-language': 'ru-RU,ru;q=0.9,en;q=0.8',
        'content-type': 'application/json',
        'referer': search_nav_url,
        'sec-ch-ua': session_message.sec_ch_ua,
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': f'"{session_message.sec_ch_ua_platform}"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': session_message.user_agent,
        'x-o3-app-name': 'dweb_client',
        'x-o3-app-version': session_message.extra['app_version'],
        'x-o3-manifest-version': OZON_FALLBACK_MANIFEST_VERSION,
        'x-page-view-id': str(uuid.uuid4()).upper(),
    }
    timeout = config.GENERATION.VALIDATION_TIMEOUT_SECONDS
    next_url = f'/search/?from_global=true&text={search_query}'

    try:
        session.get(url=search_nav_url, headers=nav_headers, timeout=timeout)
        response = session.get(
            url=OZON_SEARCH_API, params={'url': next_url}, headers=api_headers, timeout=timeout,
        )
    except Exception as exc:
        logger.warning('[validation_failed] marketplace=ozon error=%s', exc)
        return False

    content_type = response.headers.get('content-type', '')
    body_prefix = response.text[:2000].lower()
    is_blocked = is_ozon_blocked_response(
        status=response.status_code, content_type=content_type, body_prefix=body_prefix,
    )
    if is_blocked:
        logger.warning('[validation_blocked] marketplace=ozon status=%d', response.status_code)
        return False
    logger.info('[validation_passed] marketplace=ozon status=%d', response.status_code)
    return True


_VALIDATORS: dict[Marketplace, Callable[[SessionMessage], bool]] = {
    Marketplace.WILDBERRIES: _validate_wb,
    Marketplace.OZON: _validate_ozon,
}


def validate_session(session_message: SessionMessage) -> bool:
    return _VALIDATORS[session_message.marketplace](session_message)
