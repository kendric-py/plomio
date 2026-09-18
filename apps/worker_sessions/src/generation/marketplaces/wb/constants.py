import re
from typing import Any

WB_BASE_URL = 'https://www.wildberries.ru'

WB_REQUIRED_COOKIES: frozenset[str] = frozenset({'x_wbaas_token'})
# _wbauid is set by a third-party analytics script (a.wb.ru/sdk/sdk.js), not by the antibot
# challenge itself — it's an anonymous tracking id, not needed to authenticate API requests
# (validated: the search API accepts a session with only x_wbaas_token). That script is prone
# to failing to load over flaky proxies, so it must not gate session generation; captured
# opportunistically when present instead.
WB_OPTIONAL_COOKIES: frozenset[str] = frozenset({'_wbauid'})

WB_FALLBACK_SPA_VERSION = '14.13.6'
# Camoufox is a Firefox-engine browser — real Firefox never sends Client Hints, so the
# consistent (and only truthful) fallback here is an empty sec-ch-ua string, not a faked
# Chrome one that would contradict the real navigator.userAgent.
WB_FALLBACK_SEC_CH_UA = ''

WB_SPA_VERSION_PATTERN = re.compile(r'website@(\d+\.\d+\.\d+)')
WB_SCRIPT_URL_PATTERN = re.compile(r'(https://[^"]+/index-spa\.[a-f0-9]+\.js)')

# Used only to validate a freshly generated session — a real search request, same endpoint
# and params fetchers use, so blocks specific to the API (not just the homepage) are caught
# before the session is stored.
WB_SEARCH_API = 'https://www.wildberries.ru/__internal/u-search/exactmatch/ru/common/v18/search'
WB_VALIDATION_QUERY = 'телефон'
WB_VALIDATION_PARAMS_BASE: dict[str, Any] = {
    'ab_testing': 'false',
    'appType': '1',
    'curr': 'rub',
    'dest': '-1257786',
    'hide_dtype': '15',
    'hide_vflags': '4294967296',
    'inheritFilters': 'false',
    'lang': 'ru',
    'locale': 'ru',
    'resultset': 'catalog',
    'sort': 'popular',
    'spp': '30',
    'suppressSpellcheck': 'false',
}

WB_STEALTH_JS = """
() => {
    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
    Object.defineProperty(navigator, 'languages', {
        get: () => ['ru-RU', 'ru', 'en-US', 'en']
    });
    Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
    Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});
    Object.defineProperty(screen, 'colorDepth', {get: () => 24});
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) =>
        parameters.name === 'notifications'
            ? Promise.resolve({state: Notification.permission})
            : originalQuery(parameters);
}
"""
