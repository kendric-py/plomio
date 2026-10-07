"""Сквозной сценарий Ozon без браузера: генерация сессии (oz_flow) → поток названий из поиска.

Запуск (из корня репозитория):  python scripts/ozon/search_stream.py

Скрипт спрашивает поисковый запрос, генерирует антибот-сессию безбраузерным путём
(`apps/worker_sessions/research/js_runtime/oz_flow.py`), затем раз в секунду печатает названия
товаров — страница выдачи за такт, пока пользователь не остановит (Ctrl+C) или не кончится выдача.
Запросы к API повторяют прод-фетчер `apps/worker_parser/src/marketplaces/ozon/fetchers.py`
(warmup-навигация → entrypoint-api, курсор `nextPage`, `x-o3-parent-requestid`).
"""
import json
import os
import sys
import time
import uuid
from urllib.parse import quote_plus

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, 'apps', 'worker_sessions', 'research', 'js_runtime'))

import oz_flow  # noqa: E402 — безбраузерная генерация сессии (curl_cffi + Node-решатель)
from apps.worker_sessions.src.generation.marketplaces.ozon.constants import (  # noqa: E402
    OZON_FALLBACK_APP_VERSION,
    OZON_FALLBACK_MANIFEST_VERSION,
)
from apps.worker_sessions.src.generation.marketplaces.ozon.utils import (  # noqa: E402
    is_ozon_blocked_response,
)

OZON_BASE_URL = 'https://www.ozon.ru'
OZON_SEARCH_API = OZON_BASE_URL + '/api/entrypoint-api.bx/page/json/v2'
PAGE_INTERVAL_S = 1.0
MAX_SESSION_REGENS = 2  # подряд, при блокировке страницы

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass


def _nav_headers(referer: str) -> dict:
    return {**oz_flow.CH, 'user-agent': oz_flow.UA,
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'accept-language': 'ru-RU,ru;q=0.9,en;q=0.8', 'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate', 'upgrade-insecure-requests': '1', 'referer': referer,
            'sec-fetch-site': 'same-origin'}


def _api_headers(referer: str, parent_request_id: str | None) -> dict:
    h = {**oz_flow.CH, 'user-agent': oz_flow.UA, 'accept': 'application/json',
         'accept-language': 'ru-RU,ru;q=0.9,en;q=0.8', 'content-type': 'application/json',
         'referer': referer, 'sec-fetch-dest': 'empty', 'sec-fetch-mode': 'cors',
         'sec-fetch-site': 'same-origin', 'x-o3-app-name': 'dweb_client',
         'x-o3-app-version': OZON_FALLBACK_APP_VERSION,
         'x-o3-manifest-version': OZON_FALLBACK_MANIFEST_VERSION,
         'x-page-view-id': str(uuid.uuid4()).upper()}
    if parent_request_id:
        h['x-o3-parent-requestid'] = parent_request_id
    return h


def _extract_new_titles(payload: dict, seen: set) -> list[str]:
    """Товары лежат в widgetStates: JSON-строки с `items`; название — mainState-запись id=='name'."""
    titles = []
    for state_raw in payload.get('widgetStates', {}).values():
        if not isinstance(state_raw, str) or '"items"' not in state_raw:
            continue
        try:
            state_object = json.loads(state_raw)
        except json.JSONDecodeError:
            continue
        for item in state_object.get('items') or []:
            if not isinstance(item, dict):
                continue
            link = item.get('action', {}).get('link')
            title = None
            for entry in item.get('mainState', []):
                if entry.get('id') == 'name':
                    title = (entry.get('textDS', {}).get('text') or '').strip()
                    break
            key = str(item.get('id') or link)
            if not title or not link or key in seen:
                continue
            seen.add(key)
            titles.append(title)
    return titles


def _extract_next_page(payload: dict) -> str | None:
    """Зеркало apps/worker_parser/src/marketplaces/ozon/pagination.py."""
    if payload.get('nextPage'):
        return payload['nextPage']
    for key, raw in payload.get('widgetStates', {}).items():
        if 'paginator' not in key.lower() or not isinstance(raw, str):
            continue
        try:
            widget = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(widget, dict) and widget.get('nextPage'):
            return widget['nextPage']
    return None


def _new_session():
    print('Генерация сессии (без браузера)...', flush=True)
    o = oz_flow.get_ozon_cookies()
    if not o['ok']:
        raise RuntimeError('сессия не прошла антибот: %s %s' % (o.get('status'), o.get('resp')))
    print('Сессия готова за %.1f с (%s)\n' % (o['total_s'], o['script'].rsplit('/', 1)[-1]), flush=True)
    return o['session']


def main() -> int:
    query = input('Поисковый запрос: ').strip()
    if not query:
        print('Пустой запрос — выход.')
        return 1

    session = _new_session()
    next_url = '/search/?from_global=true&text=' + quote_plus(query)
    referer = OZON_BASE_URL + '/'
    parent_request_id = None
    seen: set = set()
    total = 0
    page_num = 0
    regens_left = MAX_SESSION_REGENS

    # warmup, как в прод-фетчере: навигация на страницу поиска перед первым API-запросом
    session.get(OZON_BASE_URL + next_url, headers=_nav_headers(referer), timeout=15)
    referer = OZON_BASE_URL + next_url

    print('Поток названий (раз в %g с). Остановка — Ctrl+C.\n' % PAGE_INTERVAL_S, flush=True)
    try:
        while next_url:
            t0 = time.monotonic()
            try:
                resp = session.get(OZON_SEARCH_API, params={'url': next_url},
                                   headers=_api_headers(referer, parent_request_id), timeout=15)
            except Exception as exc:
                print('! сбой запроса: %s — повтор через 1 с' % exc, flush=True)
                time.sleep(1.0)
                continue
            if is_ozon_blocked_response(resp.status_code, resp.headers.get('content-type', ''),
                                        resp.text[:2000].lower()):
                if regens_left <= 0:
                    print('! антибот не пускает повторно — стоп.')
                    break
                regens_left -= 1
                print('! страница заблокирована (HTTP %s) — новая сессия...' % resp.status_code, flush=True)
                session = _new_session()
                session.get(OZON_BASE_URL + next_url, headers=_nav_headers(OZON_BASE_URL + '/'), timeout=15)
                continue
            regens_left = MAX_SESSION_REGENS
            payload = resp.json()
            page_num += 1
            titles = _extract_new_titles(payload, seen)
            print('— страница %d: %d новых' % (page_num, len(titles)), flush=True)
            for title in titles:
                total += 1
                print('[%d] %s' % (total, title), flush=True)
            next_page = _extract_next_page(payload)
            if next_page is None:
                print('\nВыдача исчерпана: %d товаров на %d страницах.' % (total, page_num))
                break
            referer = OZON_BASE_URL + payload.get('pageInfo', {}).get('url', '')
            parent_request_id = payload.get('requestID')
            next_url = next_page
            time.sleep(max(0.0, PAGE_INTERVAL_S - (time.monotonic() - t0)))
    except KeyboardInterrupt:
        print('\nОстановлено пользователем.')
    print('Итого: %d товаров, %d страниц.' % (total, page_num))
    return 0


if __name__ == '__main__':
    sys.exit(main())
