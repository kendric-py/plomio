"""Сквозной сценарий Wildberries без браузера: антибот-токен (wb_flow_warm) → поток названий из поиска.

Запуск (из корня репозитория):  python scripts/wb/search_stream.py

Скрипт спрашивает поисковый запрос, поднимает постоянный Node-решатель и получает токен
`x_wbaas_token` безбраузерным путём (`apps/worker_sessions/js_runtime/ready/wb/wb_flow_warm.py`),
затем раз в секунду печатает названия товаров — страница выдачи за такт, пока пользователь не
остановит (Ctrl+C) или не кончится выдача. Запросы к API повторяют прод-фетчер
`apps/worker_parser/src/marketplaces/wb/fetchers.py` (прогрев главной и страницы поиска,
пагинация `page=N`, правила конца выдачи и деградации сессии — те же).
"""
import os
import sys
import time
import uuid
from urllib.parse import quote_plus

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, 'apps', 'worker_sessions', 'js_runtime', 'ready', 'wb'))

from curl_cffi.requests import Session  # noqa: E402
from wb_flow import UA, HOST  # noqa: E402 — Firefox-135 идентичность, под которую выдаётся токен
from wb_flow_warm import NodeSolver, get_token  # noqa: E402 — безбраузерный токен (теплый Node)
from apps.worker_parser.src.marketplaces.wb.constants import (  # noqa: E402
    WB_SEARCH_API,
    WB_SEARCH_PAGE_LIMIT_ERROR,
    WB_SEARCH_PARAMS_BASE,
)
from apps.worker_parser.src.marketplaces.wb.utils import (  # noqa: E402
    get_raw_wb_products,
    is_degraded_wb_listing,
)
from apps.worker_sessions.src.generation.marketplaces.wb.utils import (  # noqa: E402
    is_wb_blocked_response,
)

WB_BASE_URL = HOST  # https://www.wildberries.ru
PAGE_INTERVAL_S = 1.0
MAX_SESSION_REGENS = 2  # подряд, при блокировке/деградации
SPA_VERSION = '14.13.6'  # как в js_runtime/debug/wb/wb_validate.py; снимок, дрейфует со временем

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass


def _make_query_id() -> str:
    import random
    import string
    return 'qid%d%s' % (int(time.time() * 1000), ''.join(random.choices(string.digits, k=10)))


def _nav_headers(referer: str | None) -> dict:
    h = {'user-agent': UA, 'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
         'accept-language': 'ru-RU,ru;q=0.9,en;q=0.8', 'sec-fetch-dest': 'document',
         'sec-fetch-mode': 'navigate', 'upgrade-insecure-requests': '1'}
    if referer:
        h['referer'] = referer
        h['sec-fetch-site'] = 'same-origin'
    else:
        h['sec-fetch-site'] = 'none'
    return h


def _api_headers(referer: str, device_id: str) -> dict:
    return {'user-agent': UA, 'accept': '*/*', 'accept-language': 'ru-RU,ru;q=0.9,en;q=0.8',
            'deviceid': device_id, 'referer': referer, 'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors', 'sec-fetch-site': 'same-origin',
            'x-queryid': _make_query_id(), 'x-requested-with': 'XMLHttpRequest',
            'x-spa-version': SPA_VERSION, 'x-userid': '0'}


def _new_session(solver: NodeSolver):
    """Свежий токен + curl-сессия с куками `x_wbaas_token`/`deviceid` (как валидатор приложения)."""
    print('Получение антибот-токена (без браузера)...', flush=True)
    o = get_token(solver)  # полный поток: GET / → settings → create-token ×2
    if not o['token']:
        raise RuntimeError('токен не выдан: %s' % str(o['resp'])[:200])
    device_id = 'site_' + uuid.uuid4().hex
    s = Session(impersonate='firefox135')
    s.cookies.set('x_wbaas_token', o['token'], domain='www.wildberries.ru')
    s.cookies.set('deviceid', device_id, domain='www.wildberries.ru')
    print('Токен готов за %.1f с\n' % o['total_s'], flush=True)
    return s, device_id


def main() -> int:
    query = input('Поисковый запрос: ').strip()
    if os.environ.get('DEBUG_STREAM'):
        print('DEBUG query:', repr(query))
    if not query:
        print('Пустой запрос — выход.')
        return 1

    solver = NodeSolver()
    try:
        session, device_id = _new_session(solver)
        search_page_url = WB_BASE_URL + '/catalog/0/search.aspx?search=' + quote_plus(query)
        seen: set = set()
        total = 0
        page_num = 0
        regens_left = MAX_SESSION_REGENS
        confirm_empty = False  # первая пустая страница требует подтверждения на новой сессии

        # прогрев, как в прод-фетчере: главная, затем страница поиска (обе навигационные)
        session.get(WB_BASE_URL + '/', headers=_nav_headers(None), timeout=15)
        session.get(search_page_url, headers=_nav_headers(WB_BASE_URL + '/'), timeout=15)

        print('Поток названий (раз в %g с). Остановка — Ctrl+C.\n' % PAGE_INTERVAL_S, flush=True)
        try:
            while True:
                t0 = time.monotonic()
                try:
                    resp = session.get(WB_SEARCH_API,
                                       params={**WB_SEARCH_PARAMS_BASE, 'query': query, 'page': str(page_num + 1)},
                                       headers=_api_headers(search_page_url, device_id), timeout=15)
                except Exception as exc:
                    print('! сбой запроса: %s — повтор через 1 с' % exc, flush=True)
                    time.sleep(1.0)
                    continue
                if is_wb_blocked_response(resp.status_code, resp.headers.get('content-type', ''),
                                          resp.text[:2000].lower()):
                    if regens_left <= 0:
                        print('! антибот не пускает повторно — стоп.')
                        break
                    regens_left -= 1
                    print('! страница заблокирована (HTTP %s) — новый токен...' % resp.status_code, flush=True)
                    session, device_id = _new_session(solver)
                    session.get(WB_BASE_URL + '/', headers=_nav_headers(None), timeout=15)
                    session.get(search_page_url, headers=_nav_headers(WB_BASE_URL + '/'), timeout=15)
                    continue
                payload = resp.json()
                if 'error' in payload:
                    if WB_SEARCH_PAGE_LIMIT_ERROR in str(payload.get('error')):
                        print('\nВыдача исчерпана (потолок WB ~60 страниц).')
                    else:
                        print('! WB вернул ошибку: %s — стоп.' % payload.get('error'))
                    break
                if is_degraded_wb_listing(payload):
                    # деградировавший ответ (data/state/version с посторонним товаром) — сессию меняем
                    if regens_left <= 0:
                        print('! сессия деградировала повторно — стоп.')
                        break
                    regens_left -= 1
                    print('! деградация сессии — новый токен...', flush=True)
                    session, device_id = _new_session(solver)
                    continue
                regens_left = MAX_SESSION_REGENS
                raw = get_raw_wb_products(payload)
                if 'products' not in payload and not raw:
                    print('\nНичего не найдено.')  # форма ответа без ключа products — конец без подтверждения
                    if os.environ.get('DEBUG_STREAM'):
                        print('DEBUG payload keys:', list(payload.keys()))
                        print('DEBUG head:', resp.text[:400])
                    break
                if not raw and not confirm_empty:
                    # первая пустая страница в нормальной форме — подтверждаем на новой сессии
                    confirm_empty = True
                    print('! пустая страница — подтверждение на новом токене...', flush=True)
                    session, device_id = _new_session(solver)
                    continue
                if not raw:
                    print('\nВыдача исчерпана: %d товаров на %d страницах.' % (total, page_num))
                    break
                page_num += 1
                new = 0
                print('— страница %d' % page_num, flush=True)
                for item in raw:
                    if not isinstance(item, dict):
                        continue
                    nm_id = item.get('id')
                    name = (item.get('name') or '').strip()
                    if nm_id is None or not name or str(nm_id) in seen:
                        continue
                    seen.add(str(nm_id))
                    total += 1
                    new += 1
                    print('[%d] %s' % (total, name), flush=True)
                if new == 0:
                    print('! страница без новых товаров — стоп.')
                    break
                time.sleep(max(0.0, PAGE_INTERVAL_S - (time.monotonic() - t0)))
        except KeyboardInterrupt:
            print('\nОстановлено пользователем.')
        print('Итого: %d товаров, %d страниц.' % (total, page_num))
        return 0
    finally:
        solver.close()


if __name__ == '__main__':
    sys.exit(main())
