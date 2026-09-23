import uuid

from apps.worker_parser.src.entities import SessionMessage
from apps.worker_parser.src.marketplaces.ozon.constants import OZON_FALLBACK_MANIFEST_VERSION


def _add_client_hints(headers: dict[str, str], session_message: SessionMessage) -> dict[str, str]:
    """Camoufox is a Firefox-engine browser, so `session_message.user_agent` is a real Firefox
    string — and real Firefox has no User-Agent Client Hints API at all (`navigator.userAgentData`
    is `undefined`), so it never sends `sec-ch-ua*` headers. `sec_ch_ua` is only non-empty when a
    session actually produced one; sending a Chrome Client Hints triplet alongside a Firefox
    user-agent is an internally inconsistent identity antibot can trivially flag."""
    if session_message.sec_ch_ua:
        headers['sec-ch-ua'] = session_message.sec_ch_ua
        headers['sec-ch-ua-mobile'] = '?0'
        headers['sec-ch-ua-platform'] = f'"{session_message.sec_ch_ua_platform}"'
    return headers


def build_ozon_navigation_headers(session_message: SessionMessage) -> dict[str, str]:
    return _add_client_hints({
        'accept': (
            'text/html,application/xhtml+xml,application/xml;'
            'q=0.9,image/avif,image/webp,*/*;q=0.8'
        ),
        'accept-language': 'ru-RU,ru;q=0.9,en;q=0.8',
        'sec-fetch-dest': 'document',
        'sec-fetch-mode': 'navigate',
        'upgrade-insecure-requests': '1',
        'user-agent': session_message.user_agent,
    }, session_message)


def build_ozon_api_headers(session_message: SessionMessage, referer: str) -> dict[str, str]:
    return _add_client_hints({
        'accept': 'application/json',
        'accept-language': 'ru-RU,ru;q=0.9,en;q=0.8',
        'content-type': 'application/json',
        'referer': referer,
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': session_message.user_agent,
        'x-o3-app-name': 'dweb_client',
        'x-o3-app-version': session_message.extra['app_version'],
        'x-o3-manifest-version': OZON_FALLBACK_MANIFEST_VERSION,
        'x-page-view-id': str(uuid.uuid4()).upper(),
    }, session_message)
