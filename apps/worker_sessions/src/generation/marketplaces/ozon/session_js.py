import logging
import random
import time
import uuid

from apps.worker_sessions.src.entities import ProxyConfig, SessionMessage
from apps.worker_sessions.src.exceptions import JsRuntimeError
from apps.worker_sessions.src.generation.js_runtime.loader import load_flow_module
from apps.worker_sessions.src.generation.marketplaces.ozon.constants import OZON_REQUIRED_COOKIES
from apps.worker_sessions.src.generation.marketplaces.ozon.utils import extract_ozon_app_version
from core.enums import Marketplace

logger = logging.getLogger(__name__)

oz_flow = load_flow_module('ozon', 'oz_flow')

# Identity the js_runtime flow speaks as: Chrome 154 user-agent over a chrome136 TLS profile.
# Consumers (validation, worker_parser) must reuse it — see `extra['impersonate']`.
OZON_JS_IMPERSONATE = 'chrome136'
_OZON_JS_PLATFORM = 'Windows'


def build_session_message(proxy: ProxyConfig | None) -> SessionMessage:
    start = time.monotonic()
    result = oz_flow.get_ozon_cookies(
        proxy=proxy.to_curl_url() if proxy else None, impersonate=OZON_JS_IMPERSONATE,
    )
    if (curl_session := result.get('session')) is not None:
        curl_session.close()  # unclosed curl handles/sockets leak fds until the container restarts
    cookies: dict[str, str] = result.get('cookies') or {}
    if not result.get('ok') or not OZON_REQUIRED_COOKIES <= cookies.keys():
        raise JsRuntimeError(
            f'ozon js_runtime failed: why={result.get("why")} status={result.get("status")} '
            f'post_ok={result.get("post_ok")} cookies={sorted(cookies)}',
        )
    logger.info(
        '[session_init] ozon js_runtime elapsed=%.2fs solve=%.2fs',
        time.monotonic() - start, result.get('solve_s', 0.0),
    )
    return SessionMessage(
        marketplace=Marketplace.OZON,
        proxy=proxy,
        cookies=cookies,
        user_agent=oz_flow.UA,
        sec_ch_ua=oz_flow.CH['sec-ch-ua'],
        sec_ch_ua_platform=_OZON_JS_PLATFORM,
        extra={
            'app_version': extract_ozon_app_version(result.get('reload_html') or ''),
            # xcid/ab-group are set by the flow's cookie jar when Ozon issues them, else generated
            # the same way the browser path does.
            'xcid': cookies.get('xcid') or uuid.uuid4().hex,
            'ab_group': cookies.get('__Secure-ab-group') or str(random.randint(1, 100)),
            'impersonate': OZON_JS_IMPERSONATE,
        },
    )
