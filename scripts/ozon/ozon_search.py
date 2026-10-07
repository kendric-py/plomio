"""Ozon product search without a browser.

Gets antibot cookies by solving the challenge in Node (see `js/`), then queries the search API.
Interactive: type a query, get product names; one request per second.

Usage:
    cd scripts/ozon && npm install      # once
    python ozon_search.py               # prompts for queries (empty line / Ctrl+C to quit)
    python ozon_search.py "телефон"     # single query
Requires: Python 3.10+, Node 18+, `pip install curl_cffi`.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid
from urllib.parse import quote_plus

from curl_cffi.requests import Session

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(HERE, '.cache')

BASE_URL = 'https://www.ozon.ru'
SEARCH_API = BASE_URL + '/api/entrypoint-api.bx/page/json/v2'
REQUEST_DELAY_S = 1.0
IMPERSONATE = 'chrome136'
UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36'
)
CLIENT_HINTS = {
    'sec-ch-ua': '"Chromium";v="154", "Google Chrome";v="154", "Not A(Brand";v="99"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
}
# Snapshot of live `x-o3-manifest-version` / appVersion; appVersion is re-read from the homepage.
FALLBACK_APP_VERSION = 'release_30-6-2026_35d481b8'
MANIFEST_VERSION = (
    'frontend-ozon-ru:a3eb349144e383363827d27cc22b89c6746e814a,'
    'checkout-render-api:658d7a993e214f39d71ac50969a4593a3a8e0189,'
    'search-render-api:48310d03704f2c4ffd36266a1be54936ef221aba,'
    'fav-render-api:4feb07757cd271fa29fd5ef84b68219b65c24228,'
    'sf-render-api:7613b842f83d7af57356f082f046a60c290a4a38,'
    'rtb-render-api:79a3ea34b45d993c7c29e094b0cb026d8e502ba7'
)
SCRIPT_URL_RE = re.compile(r'<script src="(https://st\.ozone\.ru/s3/abt-challenge/script_[^"]+\.js)"')
APP_VERSION_RE = re.compile(r'"appVersion"\s*:\s*"([^"]+)"')


class OzonError(RuntimeError):
    pass


def _nav_headers(**extra):
    return {
        **CLIENT_HINTS,
        'user-agent': UA,
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'accept-language': 'ru-RU,ru;q=0.9',
        'upgrade-insecure-requests': '1',
        'sec-fetch-dest': 'document',
        'sec-fetch-mode': 'navigate',
        'sec-fetch-site': 'none',
        'sec-fetch-user': '?1',
        **extra,
    }


def _challenge_script(session: Session, url: str) -> str:
    """Challenge scripts are versioned by file name, so they are cached on disk."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, url.rsplit('/', 1)[-1])
    if not os.path.exists(path):
        with open(path, 'w', encoding='utf8') as f:
            f.write(session.get(url, headers={'user-agent': UA}).text)
    return path


def _solve_challenge(html: str, script_path: str) -> dict:
    """Runs the challenge in Node, returns {'url', 'body'} for POST /abt/result."""
    with tempfile.NamedTemporaryFile('w', suffix='.html', delete=False, encoding='utf8') as f:
        f.write(html)
        html_path = f.name
    try:
        proc = subprocess.run(
            ['node', os.path.join(HERE, 'js', 'solver.js'), html_path, script_path, UA],
            capture_output=True, text=True, timeout=40, encoding='utf8',
        )
    finally:
        os.unlink(html_path)
    if proc.returncode:
        raise OzonError(f'solver failed: {proc.stderr[-500:]}')
    return json.loads(proc.stdout)


def open_session(proxy: str | None = None) -> tuple[Session, str]:
    """Returns (session with antibot cookies, appVersion)."""
    session = Session(impersonate=IMPERSONATE, proxies={'http': proxy, 'https': proxy} if proxy else None)
    resp = session.get(BASE_URL + '/', headers=_nav_headers(), allow_redirects=True)
    match = SCRIPT_URL_RE.search(resp.text)
    if not match:
        raise OzonError(f'no challenge on homepage (status {resp.status_code})')

    solution = _solve_challenge(resp.text, _challenge_script(session, match.group(1)))
    post_url = solution['url']
    if post_url.startswith('/'):
        post_url = BASE_URL + post_url
    result = session.post(
        post_url,
        data=solution['body'],
        headers={
            **CLIENT_HINTS,
            'user-agent': UA,
            'accept': '*/*',
            'accept-language': 'ru-RU,ru;q=0.9',
            'content-type': 'application/json;charset=UTF-8',
            'origin': BASE_URL,
            'referer': str(resp.url),
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
        },
    )
    if '"ok":true' not in result.text.replace(' ', ''):
        raise OzonError(f'challenge rejected: {result.status_code} {result.text[:200]}')

    # The cookies are issued on the first page load AFTER the challenge was accepted.
    home = session.get(BASE_URL + '/', headers=_nav_headers(**{'sec-fetch-site': 'same-origin'}))
    if '__Secure-access-token' not in session.cookies.get_dict():
        raise OzonError(f'no access token after challenge (status {home.status_code})')
    version = APP_VERSION_RE.search(home.text)
    return session, version.group(1) if version else FALLBACK_APP_VERSION


def search_raw(session: Session, app_version: str, query: str) -> dict:
    page_url = f'/search/?from_global=true&text={quote_plus(query)}'
    referer = BASE_URL + page_url
    response = session.get(
        SEARCH_API,
        params={'url': page_url},
        headers={
            **CLIENT_HINTS,
            'user-agent': UA,
            'accept': 'application/json',
            'accept-language': 'ru-RU,ru;q=0.9',
            'content-type': 'application/json',
            'referer': referer,
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'x-o3-app-name': 'dweb_client',
            'x-o3-app-version': app_version,
            'x-o3-manifest-version': MANIFEST_VERSION,
            'x-page-view-id': str(uuid.uuid4()).upper(),
        },
    )
    data = response.json()
    if 'challengeURL' in data:
        raise OzonError('blocked by antibot (session expired?)')
    return data


def extract_names(data: dict) -> list[str]:
    raise NotImplementedError


def main() -> None:
    queries = sys.argv[1:]
    print('Получаю сессию…')
    started = time.monotonic()
    session, app_version = open_session()
    print(f'Сессия готова за {time.monotonic() - started:.1f} с')

    last_request = 0.0
    while True:
        if queries:
            query = queries.pop(0)
        else:
            try:
                query = input('\nПоисковый запрос (пусто — выход): ').strip()
            except (EOFError, KeyboardInterrupt):
                break
        if not query:
            break

        wait = REQUEST_DELAY_S - (time.monotonic() - last_request)
        if wait > 0:
            time.sleep(wait)
        last_request = time.monotonic()
        try:
            names = extract_names(search_raw(session, app_version, query))
        except OzonError as exc:
            print(f'Ошибка: {exc}. Обновляю сессию…')
            session, app_version = open_session()
            continue
        if not names:
            print('Ничего не найдено')
        for i, name in enumerate(names, 1):
            print(f'{i:>3}. {name}')
        if len(sys.argv) > 1 and not queries:
            break


if __name__ == '__main__':
    main()
