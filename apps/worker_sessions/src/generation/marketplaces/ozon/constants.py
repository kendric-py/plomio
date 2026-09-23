import json
import re

from apps.worker_sessions.src.generation.marketplaces.ozon.fingerprint import OzonFingerprintProfile

OZON_BASE_URL = 'https://www.ozon.ru'
OZON_REQUIRED_COOKIES: frozenset[str] = frozenset({'abt_data', '__Secure-ETC', 'rfuid'})
# Captured when present but never gate the poll loop (see `_run_browser`'s `optional_cookies`
# param) — a real browser session always carries these alongside `abt_data`/`__Secure-ETC`
# (confirmed live: a genuine session with the full set survived 8 rapid consecutive search-API
# calls with zero blocks, while our 3-cookie sessions were getting blocked after 3-4 requests).
# Sending `abt_data` without its matching access/refresh-token pair is itself an anomaly
# signature — anonymous-session tokens, not auth in the "logged in user" sense.
OZON_OPTIONAL_COOKIES: frozenset[str] = frozenset({
    '__Secure-access-token', '__Secure-refresh-token', '__Secure-user-id', '__Secure-ext_xcid',
})

OZON_FALLBACK_APP_VERSION = 'release_30-6-2026_35d481b8'
OZON_APP_VERSION_PATTERN = re.compile(r'"appVersion"\s*:\s*"([^"]+)"')

# Empty on purpose — Camoufox is a Firefox-engine browser (see the comment on `_validate_wb`
# in `generation/validation.py`), and Firefox has no User-Agent Client Hints API at all
# (`navigator.userAgentData` is `undefined`), so it never sends `sec-ch-ua*` headers. A
# non-empty fallback here used to paper over that with a hardcoded Chrome Client Hints string,
# which meant every Ozon session sent a real Firefox `user-agent` alongside Chrome-only
# `sec-ch-ua*` headers — a combination no real browser produces and an easy antibot tell.
# Downstream header builders only add `sec-ch-ua*` when this is non-empty.
OZON_FALLBACK_SEC_CH_UA = ''

# Used only to validate a freshly generated session — a real search request, same endpoint
# and headers fetchers use, so blocks specific to the API (not just the homepage) are caught
# before the session is stored.
OZON_SEARCH_API = 'https://www.ozon.ru/api/entrypoint-api.bx/page/json/v2'
OZON_VALIDATION_QUERY = 'телефон'
# Snapshot of the real `x-o3-manifest-version` captured from live traffic on 2026-09-23 — the
# previous value was months stale (a different build entirely). This will drift again over
# time since it's tied to Ozon's current static-asset deploy; there's no cheap way to derive
# it per-session today, so it's a hardcoded snapshot like `OZON_FALLBACK_APP_VERSION`.
OZON_FALLBACK_MANIFEST_VERSION = (
    'frontend-ozon-ru:a3eb349144e383363827d27cc22b89c6746e814a,'
    'checkout-render-api:658d7a993e214f39d71ac50969a4593a3a8e0189,'
    'search-render-api:48310d03704f2c4ffd36266a1be54936ef221aba,'
    'fav-render-api:4feb07757cd271fa29fd5ef84b68219b65c24228,'
    'sf-render-api:7613b842f83d7af57356f082f046a60c290a4a38,'
    'rtb-render-api:79a3ea34b45d993c7c29e094b0cb026d8e502ba7'
)

# `{{`/`}}` are literal JS braces escaped for str.format(); `{languages_json}` etc. are the
# only real placeholders, filled in per-session by build_ozon_stealth_js from a fingerprint
# profile so every generated session gets internally-consistent navigator.* values.
_STEALTH_JS_TEMPLATE = """
() => {{
    Object.defineProperty(navigator, 'webdriver', {{get: () => undefined}});
    Object.defineProperty(navigator, 'plugins', {{
        get: () => {{
            const arr = [
                {{name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer'}},
                {{name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai'}},
                {{name: 'Native Client', filename: 'internal-nacl-plugin'}},
            ];
            arr.__proto__ = PluginArray.prototype;
            return arr;
        }}
    }});
    Object.defineProperty(navigator, 'languages', {{
        get: () => {languages_json}
    }});
    Object.defineProperty(navigator, 'hardwareConcurrency', {{
        get: () => {hardware_concurrency}
    }});
    Object.defineProperty(navigator, 'deviceMemory', {{get: () => {device_memory}}});
    Object.defineProperty(screen, 'colorDepth', {{get: () => {color_depth}}});
    if (navigator.userAgentData) {{
        const brands = [
            {{brand: 'Chromium', version: '136'}},
            {{brand: 'Google Chrome', version: '136'}},
            {{brand: 'Not.A/Brand', version: '99'}},
        ];
        Object.defineProperty(navigator, 'userAgentData', {{
            get: () => ({{
                brands,
                mobile: false,
                platform: 'Windows',
                getHighEntropyValues: (hints) => Promise.resolve({{
                    brands,
                    mobile: false,
                    platform: 'Windows',
                    platformVersion: '10.0.0',
                    architecture: 'x86',
                    bitness: '64',
                    model: '',
                    uaFullVersion: '136.0.0.0',
                    fullVersionList: brands,
                }}),
            }}),
        }});
    }}
    window.chrome = {{
        app: {{isInstalled: false}},
        runtime: {{connect: () => {{}}, sendMessage: () => {{}}}},
    }};
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) =>
        parameters.name === 'notifications'
            ? Promise.resolve({{state: Notification.permission}})
            : originalQuery(parameters);
}}
"""


def build_ozon_stealth_js(profile: OzonFingerprintProfile) -> str:
    return _STEALTH_JS_TEMPLATE.format(
        languages_json=json.dumps(profile.languages),
        hardware_concurrency=profile.hardware_concurrency,
        device_memory=profile.device_memory,
        color_depth=profile.color_depth,
    )
