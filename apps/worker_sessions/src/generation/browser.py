import asyncio
import atexit
import logging
import threading
import time
from typing import Any, Callable
from urllib.parse import urlparse

from camoufox.async_api import AsyncCamoufox
from playwright.async_api import Browser, Route
from pydantic import BaseModel, Field

from apps.worker_sessions.src.config import config
from apps.worker_sessions.src.exceptions import BrowserInitError
from apps.worker_sessions.src.generation.socks5_tunnel.server import Socks5Tunnel

logger = logging.getLogger(__name__)

# Resource types a session doesn't need: only the antibot cookies and the page HTML are read.
_BLOCKED_RESOURCE_TYPES = frozenset({'image', 'media', 'font'})
_COOKIE_POLL_TIMEOUT_S = 60
# After the required cookies appear, optional ones (set by slower scripts) get a short grace
# period — they never gate the session, see `optional_cookies` in `_collect_session`.
_OPTIONAL_COOKIES_GRACE_S = 0.5
_JANITOR_INTERVAL_S = 10


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


async def _with_navigation_retry(page: Any, action: Callable[[], Any], attempts: int = 5) -> Any:
    """Runs a page read, waiting for the page to settle and retrying when it fails because
    a navigation destroyed the execution context mid-call."""
    for attempt in range(1, attempts + 1):
        try:
            await page.wait_for_load_state('domcontentloaded', timeout=15_000)
            return await action()
        except Exception as exc:
            if 'Execution context was destroyed' not in str(exc) or attempt == attempts:
                raise
            await asyncio.sleep(0.5 * attempt)


async def _block_heavy_resources(route: Route) -> None:
    if route.request.resource_type in _BLOCKED_RESOURCE_TYPES:
        await route.abort()
    else:
        await route.continue_()


class _PooledBrowser:
    """One live Camoufox process (plus its SOCKS5 bridge) shared by many sessions, each in its
    own isolated browser context. Starting Firefox is the biggest fixed cost of a generation,
    so it is paid once per proxy for up to `BROWSER_MAX_USES` sessions instead of every time."""

    def __init__(
        self,
        proxy_url: str | None,
        manager: Any,
        browser: Browser,
        tunnel: Socks5Tunnel | None,
    ) -> None:
        self.proxy_url = proxy_url
        self.browser = browser
        self._manager = manager
        self._tunnel = tunnel
        self.created_at = time.monotonic()
        self.last_used_at = self.created_at
        self.uses = 0
        self.active = 0
        self.retired = False

    def is_reusable(self) -> bool:
        generation = config.GENERATION
        return (
            not self.retired
            and self.browser.is_connected()
            and self.uses < generation.BROWSER_MAX_USES
            and time.monotonic() - self.created_at < generation.BROWSER_MAX_AGE_S
        )

    def is_disposable(self) -> bool:
        """Idle and no longer worth keeping: retired, aged out, dead or unused for too long."""
        if self.active:
            return False
        idle = time.monotonic() - self.last_used_at
        return not self.is_reusable() or idle > config.GENERATION.BROWSER_IDLE_TTL_S

    async def close(self) -> None:
        try:
            await self._manager.__aexit__(None, None, None)
        except Exception:
            logger.warning('[browser_close_failed] proxy=%s', self.proxy_url, exc_info=True)
        finally:
            if self._tunnel is not None:
                await self._tunnel.stop()


class _BrowserPool:
    """Keeps warm browsers on a dedicated event-loop thread, so the synchronous generation
    code (running on executor threads) can reuse them between calls."""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._start_lock = threading.Lock()
        self._entries: list[_PooledBrowser] = []
        self._create_lock: asyncio.Lock | None = None

    def run(self, coroutine: Any, timeout: float) -> Any:
        loop = self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(coroutine, loop)
        try:
            return future.result(timeout=timeout)
        except BaseException:
            future.cancel()
            raise

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        with self._start_lock:
            if self._loop is None:
                loop = asyncio.new_event_loop()
                threading.Thread(
                    target=self._serve, args=(loop,), name='browser-pool', daemon=True,
                ).start()
                asyncio.run_coroutine_threadsafe(self._init_in_loop(), loop).result(timeout=5)
                self._loop = loop
            return self._loop

    @staticmethod
    def _serve(loop: asyncio.AbstractEventLoop) -> None:
        asyncio.set_event_loop(loop)
        loop.run_forever()

    async def _init_in_loop(self) -> None:
        self._create_lock = asyncio.Lock()
        asyncio.create_task(self._janitor())

    async def acquire(self, proxy_url: str | None) -> _PooledBrowser:
        assert self._create_lock is not None
        async with self._create_lock:
            for entry in self._entries:
                if entry.proxy_url == proxy_url and entry.is_reusable():
                    break
            else:
                entry = await self._launch(proxy_url=proxy_url)
                self._entries.append(entry)
            entry.uses += 1
            entry.active += 1
            return entry

    async def release(self, entry: _PooledBrowser, failed: bool) -> None:
        entry.active -= 1
        entry.last_used_at = time.monotonic()
        if failed:
            # A crashed/hung session may have left the browser in a bad state — don't reuse it.
            entry.retired = True
        if entry.is_disposable():
            await self._discard(entry)

    async def _discard(self, entry: _PooledBrowser) -> None:
        if entry in self._entries:
            self._entries.remove(entry)
        await entry.close()

    async def _launch(self, proxy_url: str | None) -> _PooledBrowser:
        proxy_config, tunnel = _build_proxy_config(proxy_url=proxy_url)
        if tunnel is not None:
            await tunnel.start()
            proxy_config = {'server': f'socks5://127.0.0.1:{tunnel.port}'}
        camoufox_kwargs: dict[str, Any] = {
            'headless': not config.DEBUG,
            'os': 'windows',
            'geoip': proxy_config is not None,  # only enable geoip when a proxy is configured
        }
        if proxy_config:
            camoufox_kwargs['proxy'] = proxy_config
        manager = AsyncCamoufox(**camoufox_kwargs)
        try:
            browser = await manager.__aenter__()
        except BaseException:
            if tunnel is not None:
                await tunnel.stop()
            raise
        return _PooledBrowser(proxy_url=proxy_url, manager=manager, browser=browser, tunnel=tunnel)

    async def _janitor(self) -> None:
        while True:
            await asyncio.sleep(_JANITOR_INTERVAL_S)
            try:
                for entry in list(self._entries):
                    if entry.is_disposable():
                        await self._discard(entry)
            except Exception:
                logger.exception('[browser_pool_janitor_error]')

    def shutdown(self) -> None:
        if self._loop is None:
            return

        async def _close_all() -> None:
            for entry in list(self._entries):
                await self._discard(entry)

        try:
            asyncio.run_coroutine_threadsafe(_close_all(), self._loop).result(timeout=10)
        except Exception:
            logger.debug('[browser_pool_shutdown_failed]', exc_info=True)


_POOL = _BrowserPool()
atexit.register(_POOL.shutdown)


async def _collect_session(
    browser: Browser,
    stealth_script: str,
    origin_url: str,
    required_cookies: frozenset[str],
    launch_options: BrowserLaunchOptions,
    optional_cookies: frozenset[str],
) -> dict[str, Any]:
    browser_context = await browser.new_context(
        no_viewport=True,
        locale=launch_options.locale,
        timezone_id=launch_options.timezone_id,
        color_scheme=launch_options.color_scheme,
        extra_http_headers=launch_options.extra_http_headers,
    )
    try:
        await browser_context.route('**/*', _block_heavy_resources)
        await browser_context.add_init_script(stealth_script)
        page = await browser_context.new_page()

        # `commit` returns as soon as the response starts — the antibot cookie arrives with the
        # challenge itself, there is no need to wait for the page to finish parsing.
        await page.goto(origin_url, wait_until='commit', timeout=30_000)

        cookies: dict[str, str] = {}
        poll_started = time.monotonic()
        required_seen_at: float | None = None
        cookie_poll_interval_seconds = 0.1
        while time.monotonic() - poll_started < _COOKIE_POLL_TIMEOUT_S:
            raw_cookies = await browser_context.cookies(origin_url)
            cookies = {cookie['name']: cookie['value'] for cookie in raw_cookies}
            if required_cookies.issubset(cookies):
                required_seen_at = required_seen_at or time.monotonic()
                grace_over = time.monotonic() - required_seen_at >= _OPTIONAL_COOKIES_GRACE_S
                if optional_cookies.issubset(cookies) or grace_over:
                    break
            await asyncio.sleep(cookie_poll_interval_seconds)
            cookie_poll_interval_seconds = min(cookie_poll_interval_seconds * 1.3, 0.3)
        else:
            raise BrowserInitError(f'challenge not passed within {_COOKIE_POLL_TIMEOUT_S} seconds')

        # The antibot may reload the page right after issuing the cookie, so reads below
        # race with a navigation — retry them once the page has settled.
        html = await _with_navigation_retry(page, lambda: page.content())
        user_agent = await _with_navigation_retry(
            page, lambda: page.evaluate('navigator.userAgent'),
        )
        sec_ch_ua = await _with_navigation_retry(
            page,
            lambda: page.evaluate(
                "(navigator.userAgentData?.brands || [])"
                ".map(brand => `\"${brand.brand}\";v=\"${brand.version}\"`)"
                ".join(', ')",
            ),
        )
        sec_ch_ua_platform = await _with_navigation_retry(
            page, lambda: page.evaluate("navigator.userAgentData?.platform || 'Windows'"),
        )
    finally:
        try:
            await browser_context.close()
        except Exception:
            logger.debug('[context_close_failed]', exc_info=True)

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


async def _run_browser(
    stealth_script: str,
    origin_url: str,
    required_cookies: frozenset[str],
    launch_options: BrowserLaunchOptions,
    optional_cookies: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    entry = await _POOL.acquire(proxy_url=launch_options.proxy_url)
    failed = False
    try:
        return await _collect_session(
            browser=entry.browser,
            stealth_script=stealth_script,
            origin_url=origin_url,
            required_cookies=required_cookies,
            launch_options=launch_options,
            optional_cookies=optional_cookies,
        )
    except BaseException:
        failed = True
        raise
    finally:
        await _POOL.release(entry, failed=failed)


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
            attempt_timeout = config.GENERATION.BROWSER_ATTEMPT_TIMEOUT_S
            result = _POOL.run(
                asyncio.wait_for(
                    _run_browser(
                        stealth_script=stealth_script,
                        origin_url=origin_url,
                        required_cookies=required_cookies,
                        launch_options=options,
                        optional_cookies=optional_cookies,
                    ),
                    timeout=attempt_timeout,
                ),
                timeout=attempt_timeout + 10,
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
                time.sleep(1.0 * attempt)
    raise BrowserInitError(
        f'{label}: browser init failed after {max_attempts} attempts: {last_error}',
    )
