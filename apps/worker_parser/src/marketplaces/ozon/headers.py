import uuid

from apps.worker_parser.src.entities import SessionMessage
from apps.worker_parser.src.marketplaces.ozon.constants import OZON_FALLBACK_MANIFEST_VERSION


def build_ozon_navigation_headers(session_message: SessionMessage) -> dict[str, str]:
    return {
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'accept-language': 'ru-RU,ru;q=0.9,en;q=0.8',
        'sec-ch-ua': session_message.sec_ch_ua,
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': f'"{session_message.sec_ch_ua_platform}"',
        'sec-fetch-dest': 'document',
        'sec-fetch-mode': 'navigate',
        'upgrade-insecure-requests': '1',
        'user-agent': session_message.user_agent,
    }


def build_ozon_api_headers(session_message: SessionMessage, referer: str) -> dict[str, str]:
    return {
        'accept': 'application/json',
        'accept-language': 'ru-RU,ru;q=0.9,en;q=0.8',
        'content-type': 'application/json',
        'referer': referer,
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
