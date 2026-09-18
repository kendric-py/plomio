import logging

import aiohttp

from worker_sessions.config import config
from worker_sessions.entities import ProxyConfig

logger = logging.getLogger(__name__)


async def get_proxy() -> ProxyConfig | None:
    """Placeholder client for the future proxy-issuing API — that endpoint doesn't exist yet
    (see apps/worker-sessions/AGENTS.md), so this returns None whenever it's unconfigured or
    unreachable, and the caller (ProxyRotator) treats that as "no proxy available right now"
    rather than an error. Swapping in the real endpoint later only requires setting
    PROXY_API_ISSUE_URL — no other code in this worker needs to change."""
    if not config.PROXY_API.ISSUE_URL:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                config.PROXY_API.ISSUE_URL,
                headers={'X-Worker-Token': config.PROXY_API.TOKEN},
                timeout=aiohttp.ClientTimeout(total=config.PROXY_API.TIMEOUT_SECONDS),
            ) as response:
                if response.status == 404:
                    logger.warning('[proxy_issue] no active proxies available')
                    return None
                if response.status != 200:
                    logger.warning('[proxy_issue] unexpected status %d', response.status)
                    return None
                data = await response.json()
    except Exception as exc:
        logger.warning('[proxy_issue] failed to fetch proxy: %s', exc)
        return None

    try:
        return ProxyConfig(
            type=data['proxy_type'],
            host=data['proxy_host'],
            port=data['proxy_port'],
            username=data.get('proxy_username'),
            password=data.get('proxy_password'),
        )
    except Exception as exc:
        logger.warning('[proxy_issue] malformed proxy response: %s', exc)
        return None


class ProxyRotator:
    """Holds one proxy at a time and hands it out for up to `max_sessions` session
    generations before transparently fetching a new one from the backend."""

    def __init__(self, max_sessions: int) -> None:
        self._max_sessions = max_sessions
        self._proxy: ProxyConfig | None = None
        self._issued_count = 0

    async def acquire(self) -> ProxyConfig | None:
        if self._proxy is None or self._issued_count >= self._max_sessions:
            new_proxy = await get_proxy()
            if new_proxy is None:
                return None
            self._proxy = new_proxy
            self._issued_count = 0
            logger.info('[proxy_rotate] acquired new proxy host=%s', new_proxy.host)
        self._issued_count += 1
        return self._proxy
