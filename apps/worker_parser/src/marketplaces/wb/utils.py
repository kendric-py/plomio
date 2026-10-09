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


# Корзины, чьи реальные хосты отличаются от таблицы `WB_BASKET_RANGES`: WB открывает новые корзины
# чаще, чем обновляется таблица. Заполняется по факту успешного ответа (`remember_wb_basket_host`),
# ключ — `vol` (диапазоны корзин выровнены по `vol`, а не по `nm_id`). Живёт до рестарта процесса.
_WB_LEARNED_BASKET_HOSTS: dict[int, str] = {}
_WB_LEARNED_BASKET_HOSTS_LIMIT = 10_000
# Сколько соседних корзин пробовать после хоста из таблицы: вверх (новые корзины) и вниз.
_WB_BASKET_PROBE_UP = 4
_WB_BASKET_PROBE_DOWN = 2


def _wb_basket_host_by_number(number: int) -> str:
    return f'basket-{number:02d}.wbbasket.ru'


def _wb_table_basket_host(vol: int) -> str:
    for low, high, host in WB_BASKET_RANGES:
        if low <= vol <= high:
            return host
    return WB_BASKET_RANGES[-1][2]


def get_wb_basket_host(nm_id: int) -> str:
    vol = nm_id // 100000
    return _WB_LEARNED_BASKET_HOSTS.get(vol) or _wb_table_basket_host(vol)


def get_wb_basket_host_candidates(nm_id: int) -> list[str]:
    """Хосты для перебора при 404 на `card.json`: известный/табличный, затем соседние корзины —
    сначала вверх (там появляются новые), потом вниз."""
    primary = get_wb_basket_host(nm_id)
    number = int(primary.split('.')[0].removeprefix('basket-'))
    neighbours = [number + step for step in range(1, _WB_BASKET_PROBE_UP + 1)]
    neighbours += [
        number - step for step in range(1, _WB_BASKET_PROBE_DOWN + 1) if number - step >= 1
    ]
    return [primary, *(_wb_basket_host_by_number(value) for value in neighbours)]


def remember_wb_basket_host(nm_id: int, host: str) -> None:
    if len(_WB_LEARNED_BASKET_HOSTS) >= _WB_LEARNED_BASKET_HOSTS_LIMIT:
        _WB_LEARNED_BASKET_HOSTS.clear()
    _WB_LEARNED_BASKET_HOSTS[nm_id // 100000] = host


def get_wb_card_json_url(nm_id: int, host: str | None = None) -> str:
    vol = nm_id // 100000
    part = nm_id // 1000
    basket = host or get_wb_basket_host(nm_id)
    return f'https://{basket}/vol{vol}/part{part}/{nm_id}/info/ru/card.json'


def is_wb_blocked_response(status: int, content_type: str, body_prefix: str) -> bool:
    if status in {401, 403, 498}:
        return True
    markers = ('wbaas', 'captcha', 'antibot')
    return any(marker in body_prefix for marker in markers)


def is_degraded_wb_listing(payload: dict[str, Any]) -> bool:
    """Деградировавший ответ сессии: нет `products` верхнего уровня, вместо него `data`/`state`/
    `version` с одним посторонним товаром (проверено на живых ответах; лечится сменой сессии).
    Нормальные ответы выдач (поиск, категория, продавец) всегда несут `products` наверху."""
    return (
        'products' not in payload and isinstance(payload.get('data'), dict) and 'state' in payload
    )


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
    kwargs: dict = {'impersonate': session_message.extra.get('impersonate', 'chrome136')}
    if session_message.proxy:
        proxy_url = session_message.proxy.to_curl_url()
        kwargs['proxies'] = {'http': proxy_url, 'https': proxy_url}
    http_session = AsyncSession(**kwargs)
    for name, value in session_message.cookies.items():
        http_session.cookies.set(name, value, domain='www.wildberries.ru')
    http_session.cookies.set(
        'deviceid', session_message.extra['device_id'], domain='www.wildberries.ru',
    )
    return http_session
