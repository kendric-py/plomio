import json
import re

from worker_sessions.generation.marketplaces.ozon.fingerprint import OzonFingerprintProfile

OZON_BASE_URL = 'https://www.ozon.ru'
OZON_REQUIRED_COOKIES: frozenset[str] = frozenset({'abt_data', '__Secure-ETC', 'rfuid'})

OZON_FALLBACK_APP_VERSION = 'release_30-6-2026_35d481b8'
OZON_APP_VERSION_PATTERN = re.compile(r'"appVersion"\s*:\s*"([^"]+)"')

OZON_FALLBACK_SEC_CH_UA = '"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"'

# Used only to validate a freshly generated session — a real search request, same endpoint
# and headers fetchers use, so blocks specific to the API (not just the homepage) are caught
# before the session is stored.
OZON_SEARCH_API = 'https://www.ozon.ru/api/entrypoint-api.bx/page/json/v2'
OZON_VALIDATION_QUERY = 'телефон'
OZON_FALLBACK_MANIFEST_VERSION = (
    'frontend-ozon-ru:35d481b8f2423751ae8d7cd0092e0182adbe0cba,'
    'fav-render-api:1cb3ef11e138dc80e268d0373db172ed2218b58b,'
    'checkout-render-api:66fd5908a3154fafcb1d2a668bba35b8324b5155,'
    'sf-render-api:59ec2fc27bef0715bc389d50205a76369ecef08a,'
    'search-render-api:25dc405c731dd2b74ef8fa0d38875ed145afdf0f'
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
