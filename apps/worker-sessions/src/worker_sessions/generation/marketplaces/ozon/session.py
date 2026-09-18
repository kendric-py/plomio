import logging
import random
import time
import uuid

from worker_sessions.entities import ProxyConfig, SessionMessage
from worker_sessions.enums import Marketplace
from worker_sessions.generation.browser import (
    BrowserLaunchOptions,
    BrowserSession,
    initialize_browser_session,
)
from worker_sessions.generation.marketplaces.ozon.constants import (
    OZON_BASE_URL,
    OZON_FALLBACK_SEC_CH_UA,
    OZON_REQUIRED_COOKIES,
    build_ozon_stealth_js,
)
from worker_sessions.generation.marketplaces.ozon.fingerprint import (
    generate_ozon_fingerprint_profile,
)
from worker_sessions.generation.marketplaces.ozon.utils import extract_ozon_app_version

logger = logging.getLogger(__name__)


def initialize_ozon_session(
    launch_options: BrowserLaunchOptions | None = None,
    proxy_url: str | None = None,
) -> BrowserSession:
    start = time.monotonic()
    options = launch_options or BrowserLaunchOptions()
    if proxy_url and not options.proxy_url:
        options = options.model_copy(update={'proxy_url': proxy_url})
    fingerprint_profile = generate_ozon_fingerprint_profile()
    browser_session = initialize_browser_session(
        stealth_script=build_ozon_stealth_js(profile=fingerprint_profile),
        origin_url=OZON_BASE_URL + '/',
        required_cookies=OZON_REQUIRED_COOKIES,
        extract_app_version=extract_ozon_app_version,
        fallback_sec_ch_ua=OZON_FALLBACK_SEC_CH_UA,
        launch_options=options,
        label='ozon',
    )
    logger.info('[session_init] ozon stage=total elapsed=%.2fs', time.monotonic() - start)
    return browser_session


def build_session_message(proxy: ProxyConfig | None) -> SessionMessage:
    browser_session = initialize_ozon_session(proxy_url=proxy.to_url() if proxy else None)
    return SessionMessage(
        marketplace=Marketplace.OZON,
        proxy=proxy,
        cookies=browser_session.cookies,
        user_agent=browser_session.user_agent,
        sec_ch_ua=browser_session.sec_ch_ua,
        sec_ch_ua_platform=browser_session.sec_ch_ua_platform,
        extra={
            'app_version': browser_session.app_version,
            'xcid': uuid.uuid4().hex,
            'ab_group': str(random.randint(1, 100)),
        },
    )
