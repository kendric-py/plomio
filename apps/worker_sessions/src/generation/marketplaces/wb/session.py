import logging
import time

from curl_cffi.requests import Session
from pydantic import BaseModel, Field

from apps.worker_sessions.src.entities import ProxyConfig, SessionMessage
from apps.worker_sessions.src.generation.browser import (
    BrowserLaunchOptions,
    initialize_browser_session,
)
from apps.worker_sessions.src.generation.marketplaces.wb.constants import (
    WB_BASE_URL,
    WB_FALLBACK_SEC_CH_UA,
    WB_FALLBACK_SPA_VERSION,
    WB_OPTIONAL_COOKIES,
    WB_REQUIRED_COOKIES,
    WB_STEALTH_JS,
)
from apps.worker_sessions.src.generation.marketplaces.wb.utils import (
    extract_wb_script_url,
    extract_wb_spa_version,
    generate_device_id,
)
from core.enums import Marketplace

logger = logging.getLogger(__name__)


class WbSession(BaseModel):
    user_agent: str = Field(...)
    sec_ch_ua: str = Field(...)
    sec_ch_ua_platform: str = Field(...)
    spa_version: str = Field(...)
    device_id: str = Field(...)
    cookies: dict[str, str] = Field(...)


def _extract_wb_spa_version(html: str) -> str:
    script_url = extract_wb_script_url(html=html)
    if not script_url:
        return WB_FALLBACK_SPA_VERSION
    try:
        session = Session(impersonate='chrome136')
        response = session.get(url=script_url, headers={'Range': 'bytes=0-500'}, timeout=10)
        return extract_wb_spa_version(html_or_script=response.text)
    except Exception:
        logger.warning('[spa_version_fallback] wb failed to fetch/parse spa version, falling back')
        return WB_FALLBACK_SPA_VERSION


def initialize_wb_session(
    launch_options: BrowserLaunchOptions | None = None,
    proxy_url: str | None = None,
) -> WbSession:
    start = time.monotonic()
    options = launch_options or BrowserLaunchOptions()
    if proxy_url and not options.proxy_url:
        options = options.model_copy(update={'proxy_url': proxy_url})
    browser_session = initialize_browser_session(
        stealth_script=WB_STEALTH_JS,
        origin_url=WB_BASE_URL + '/',
        required_cookies=WB_REQUIRED_COOKIES,
        extract_app_version=_extract_wb_spa_version,
        fallback_sec_ch_ua=WB_FALLBACK_SEC_CH_UA,
        launch_options=options,
        label='wb',
        optional_cookies=WB_OPTIONAL_COOKIES,
    )
    session = WbSession(
        user_agent=browser_session.user_agent,
        sec_ch_ua=browser_session.sec_ch_ua,
        sec_ch_ua_platform=browser_session.sec_ch_ua_platform,
        spa_version=browser_session.app_version,
        device_id=generate_device_id(),
        cookies=browser_session.cookies,
    )
    logger.info('[session_init] wb stage=total elapsed=%.2fs', time.monotonic() - start)
    return session


def build_session_message(proxy: ProxyConfig | None) -> SessionMessage:
    wb_session = initialize_wb_session(proxy_url=proxy.to_url() if proxy else None)
    return SessionMessage(
        marketplace=Marketplace.WILDBERRIES,
        proxy=proxy,
        cookies=wb_session.cookies,
        user_agent=wb_session.user_agent,
        sec_ch_ua=wb_session.sec_ch_ua,
        sec_ch_ua_platform=wb_session.sec_ch_ua_platform,
        extra={'device_id': wb_session.device_id, 'spa_version': wb_session.spa_version},
    )
