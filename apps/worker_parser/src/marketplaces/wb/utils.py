import re
from typing import Any
from urllib.parse import parse_qs, urlparse

from curl_cffi.requests import AsyncSession

from apps.worker_parser.src.entities import SessionMessage
from apps.worker_parser.src.marketplaces.wb.constants import WB_BASKET_RANGES


def extract_wb_nm_id_from_url(url: str) -> int | None:
    match = re.search(r'/catalog/(\d+)/', url)
    return int(match.group(1)) if match else None


def extract_wb_size_option_id_from_url(url: str) -> int | None:
    values = parse_qs(urlparse(url).query).get('size')
    if not values:
        return None
    try:
        return int(values[0])
    except ValueError:
        return None


def extract_wb_supplier_id_from_url(url: str) -> int | None:
    match = re.search(r'/seller/(\d+)', url)
    return int(match.group(1)) if match else None


def get_wb_basket_host(nm_id: int) -> str:
    vol = nm_id // 100000
    for low, high, host in WB_BASKET_RANGES:
        if low <= vol <= high:
            return host
    return WB_BASKET_RANGES[-1][2]


def get_wb_card_json_url(nm_id: int) -> str:
    vol = nm_id // 100000
    part = nm_id // 1000
    host = get_wb_basket_host(nm_id)
    return f'https://{host}/vol{vol}/part{part}/{nm_id}/info/ru/card.json'


def is_wb_blocked_response(status: int, content_type: str, body_prefix: str) -> bool:
    if status in {401, 403, 498}:
        return True
    markers = ('wbaas', 'captcha', 'antibot')
    return any(marker in body_prefix for marker in markers)


def get_raw_wb_products(payload: dict[str, Any]) -> list[Any]:
    top = payload.get('products')
    if top:
        return top
    data = payload.get('data')
    if isinstance(data, dict):
        nested = data.get('products')
        if nested:
            return nested
    return []


def create_wb_http_session(session_message: SessionMessage) -> AsyncSession:
    kwargs: dict = {'impersonate': 'chrome136'}
    if session_message.proxy:
        proxy_url = session_message.proxy.to_url()
        kwargs['proxies'] = {'http': proxy_url, 'https': proxy_url}
    http_session = AsyncSession(**kwargs)
    for name, value in session_message.cookies.items():
        http_session.cookies.set(name, value, domain='www.wildberries.ru')
    http_session.cookies.set(
        'deviceid', session_message.extra['device_id'], domain='www.wildberries.ru',
    )
    return http_session
