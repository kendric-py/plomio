import asyncio
import logging
import random
import time
from typing import Any, Callable
from urllib.parse import urlparse

from camoufox.async_api import AsyncCamoufox
from pydantic import BaseModel, Field

from apps.worker_sessions.src.config import config
from apps.worker_sessions.src.exceptions import BrowserInitError
from apps.worker_sessions.src.generation.socks5_tunnel.server import Socks5Tunnel

logger = logging.getLogger(__name__)


class BrowserLaunchOptions(BaseModel):
    locale: str = Field(default='ru-RU')
    timezone_id: str = Field(default='Europe/Moscow')
    color_scheme: str = Field(default='light')
    extra_http_headers: dict[str, str] = Field(
        default_factory=lambda: {'accept-language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7'},
    )
    proxy_url: str | None = Field(default=None)


class BrowserSession(BaseModel):
    user_agent: str = Field(...)
    sec_ch_ua: str = Field(...)
    sec_ch_ua_platform: str = Field(...)
    cookies: dict[str, str] = Field(...)
    app_version: str = Field(...)


def _build_proxy_config(proxy_url: str | None) -> tuple[dict[str, str] | None, Socks5Tunnel | None]:
    if not proxy_url:
        return None, None
    parsed = urlparse(proxy_url)
    if parsed.scheme == 'socks5' and parsed.username:
        tunnel = Socks5Tunnel(
            host=parsed.hostname,
            port=parsed.port,
            username=parsed.username,
            password=parsed.password,
        )
        return None, tunnel
    proxy_config: dict[str, str] = {'server': f'{parsed.scheme}://{parsed.hostname}:{parsed.port}'}
    if parsed.username:
        proxy_config['username'] = parsed.username
    if parsed.password:
        proxy_config['password'] = parsed.password
    return proxy_config, None


async def _run_browser(
    stealth_script: str,
    origin_url: str,
    required_cookies: frozenset[str],
    launch_options: BrowserLaunchOptions,
    optional_cookies: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    proxy_config, tunnel = _build_proxy_config(proxy_url=launch_options.proxy_url)
    if tunnel is not None:
        await tunnel.start()
        proxy_config = {'server': f'socks5://127.0.0.1:{tunnel.port}'}

    try:
        camoufox_kwargs: dict[str, Any] = {
            'headless': not config.DEBUG,
            'os': 'windows',
            'geoip': proxy_config is not None,  # only enable geoip when a proxy is configured
        }
        if proxy_config:
            camoufox_kwargs['proxy'] = proxy_config

        async with AsyncCamoufox(**camoufox_kwargs) as browser:
            browser_context = await browser.new_context(
                no_viewport=True,
                locale=launch_options.locale,
                timezone_id=launch_options.timezone_id,
                color_scheme=launch_options.color_scheme,
                extra_http_headers=launch_options.extra_http_headers,
            )
            await browser_context.add_init_script(stealth_script)
            page = await browser_context.new_page()

            await page.goto(origin_url, wait_until='domcontentloaded', timeout=30_000)
            await asyncio.sleep(random.uniform(0.8, 1.8))

            cookies: dict[str, str] = {}
            cookie_poll_deadline = time.monotonic() + 60
            cookie_poll_interval_seconds = 0.1
            while time.monotonic() < cookie_poll_deadline:
                raw_cookies = await browser_context.cookies(origin_url)
                cookies = {cookie['name']: cookie['value'] for cookie in raw_cookies}
                if required_cookies.issubset(cookies):
                    break
                await asyncio.sleep(cookie_poll_interval_seconds)
                cookie_poll_interval_seconds = min(cookie_poll_interval_seconds * 1.3, 0.5)
            else:
                raise BrowserInitError('challenge not passed within 60 seconds')

            html = await page.content()
            user_agent = await page.evaluate('navigator.userAgent')
            sec_ch_ua = await page.evaluate(
                "(navigator.userAgentData?.brands || [])"
                ".map(brand => `\"${brand.brand}\";v=\"${brand.version}\"`)"
                ".join(', ')",
            )
            sec_ch_ua_platform = await page.evaluate(
                "navigator.userAgentData?.platform || 'Windows'",
            )

            await asyncio.sleep(2.0)

    finally:
        if tunnel:
            await tunnel.stop()

    # Optional cookies (e.g. third-party analytics IDs) are captured when present but never
    # gate the poll loop — a flaky third-party script shouldn't fail an otherwise-valid session.
    captured_cookies = {name: cookies[name] for name in required_cookies}
    captured_cookies.update({name: cookies[name] for name in optional_cookies if name in cookies})

    return {
        'cookies': captured_cookies,
        'html': html,
        'user_agent': user_agent,
        'sec_ch_ua': sec_ch_ua,
        'sec_ch_ua_platform': sec_ch_ua_platform,
    }


def initialize_browser_session(
    stealth_script: str,
    origin_url: str,
    required_cookies: frozenset[str],
    extract_app_version: Callable[[str], str],
    fallback_sec_ch_ua: str,
    launch_options: BrowserLaunchOptions | None = None,
    max_attempts: int = 3,
    label: str = 'browser',
    optional_cookies: frozenset[str] = frozenset(),
) -> BrowserSession:
    options = launch_options or BrowserLaunchOptions()
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            result = asyncio.run(
                asyncio.wait_for(
                    _run_browser(
                        stealth_script=stealth_script,
                        origin_url=origin_url,
                        required_cookies=required_cookies,
                        launch_options=options,
                        optional_cookies=optional_cookies,
                    ),
                    timeout=config.GENERATION.BROWSER_ATTEMPT_TIMEOUT_S,
                ),
            )
            return BrowserSession(
                user_agent=result['user_agent'],
                sec_ch_ua=result['sec_ch_ua'] or fallback_sec_ch_ua,
                sec_ch_ua_platform=result['sec_ch_ua_platform'],
                cookies=result['cookies'],
                app_version=extract_app_version(result['html']),
            )
        except Exception as exc:
            # Broad on purpose: Camoufox/Playwright can crash the underlying Node.js driver
            # process on malformed page-error events from the target site, which surfaces as
            # a plain Exception, not a BrowserInitError. Any failure to produce a usable
            # session should be retried the same way, up to max_attempts.
            last_error = exc
            logger.warning(
                '[browser_init_retry] %s attempt=%d/%d error=%s: %s',
                label, attempt, max_attempts, type(exc).__name__, exc,
            )
            if attempt < max_attempts:
                time.sleep(5 * attempt)
    raise BrowserInitError(
        f'{label}: browser init failed after {max_attempts} attempts: {last_error}',
    )
