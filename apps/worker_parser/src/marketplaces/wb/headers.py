import random
import string
import time

from apps.worker_parser.src.entities import SessionMessage


def _make_wb_query_id() -> str:
    timestamp = str(int(time.time() * 1000))
    random_digits = ''.join(random.choices(string.digits, k=10))
    return f'qid{timestamp}{random_digits}'


def build_wb_navigation_headers(session_message: SessionMessage) -> dict[str, str]:
    return {
        'accept': (
            'text/html,application/xhtml+xml,application/xml;'
            'q=0.9,image/avif,image/webp,*/*;q=0.8'
        ),
        'accept-language': 'ru-RU,ru;q=0.9,en;q=0.8',
        'sec-ch-ua': session_message.sec_ch_ua,
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': f'"{session_message.sec_ch_ua_platform}"',
        'sec-fetch-dest': 'document',
        'sec-fetch-mode': 'navigate',
        'upgrade-insecure-requests': '1',
        'user-agent': session_message.user_agent,
    }


def build_wb_api_headers(session_message: SessionMessage, referer: str) -> dict[str, str]:
    return {
        'accept': '*/*',
        'accept-language': 'ru-RU,ru;q=0.9,en;q=0.8',
        'deviceid': session_message.extra['device_id'],
        'referer': referer,
        'sec-ch-ua': session_message.sec_ch_ua,
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': f'"{session_message.sec_ch_ua_platform}"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': session_message.user_agent,
        'x-queryid': _make_wb_query_id(),
        'x-requested-with': 'XMLHttpRequest',
        'x-spa-version': session_message.extra['spa_version'],
        'x-userid': '0',
    }


def build_wb_cdn_headers(session_message: SessionMessage, referer: str) -> dict[str, str]:
    return {
        'accept': '*/*',
        'accept-language': 'ru-RU,ru;q=0.9,en;q=0.8',
        'referer': referer,
        'sec-ch-ua': session_message.sec_ch_ua,
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': f'"{session_message.sec_ch_ua_platform}"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'cross-site',
        'user-agent': session_message.user_agent,
    }
