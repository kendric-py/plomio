import logging

import aiohttp
from pydantic import BaseModel, Field

from apps.worker_sessions.src.config import config
from apps.worker_sessions.src.entities import ProxyConfig
from core.enums import Marketplace
from packages.sessions.src.enums import SessionGenerationOutcome

logger = logging.getLogger(__name__)


class IssuedProxy(BaseModel):
    """Выданный прокси + его id в пуле api (`ProxyConfig` его не содержит — это wire-контракт с
    `worker_parser`, id нужен только этому воркеру для записи ошибок генерации по прокси)."""

    proxy_id: int = Field(...)
    config: ProxyConfig = Field(...)


async def get_proxy() -> IssuedProxy | None:
    """Placeholder client for the future proxy-issuing API — that endpoint doesn't exist yet
    (see apps/worker_sessions/AGENTS.md), so this returns None whenever it's unconfigured or
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
        return IssuedProxy(
            proxy_id=data['proxy_id'],
            config=ProxyConfig(
                type=data['proxy_type'],
                host=data['proxy_host'],
                port=data['proxy_port'],
                username=data.get('proxy_username'),
                password=data.get('proxy_password'),
            ),
        )
    except Exception as exc:
        logger.warning('[proxy_issue] malformed proxy response: %s', exc)
        return None


# Отчёт об итоге генерации не должен подолгу задерживать цикл воркера, поэтому свой короткий
# таймаут, а не общий `PROXY_API_TIMEOUT_SECONDS` (он рассчитан на выдачу прокси).
REPORT_TIMEOUT_SECONDS = 10.0


async def report_generation(
    marketplace: Marketplace,
    outcome: SessionGenerationOutcome,
    proxy_id: int | None,
    traceback_text: str | None = None,
) -> None:
    """Сообщает api итог попытки генерации — успех или ошибку (`POST /api/proxy/generations`):
    api пишет его в БД, оттуда считаются процент успеха в пуле и статистика прокси. Вспомогательная:
    любой сбой только логируется, цикл генерации не ломает. Без `PROXY_API_ISSUE_URL` статистика не
    пишется — воркеру некуда отправить."""
    if not config.PROXY_API.ISSUE_URL:
        return
    generations_url = f"{config.PROXY_API.ISSUE_URL.removesuffix('/issue')}/generations"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                generations_url,
                json={
                    'proxy_id': proxy_id,
                    'marketplace': marketplace.value,
                    'outcome': outcome.value,
                    'traceback': traceback_text,
                },
                headers={'X-Worker-Token': config.PROXY_API.TOKEN},
                timeout=aiohttp.ClientTimeout(total=REPORT_TIMEOUT_SECONDS),
            ) as response:
                if response.status != 204:
                    logger.warning('[generation_report] unexpected status %d', response.status)
    except Exception as exc:
        logger.warning('[generation_report] failed to report: %s', exc)


class ProxyRotator:
    """Holds one proxy at a time and hands it out for up to `max_sessions` session
    generations before transparently fetching a new one from the backend."""

    def __init__(self, max_sessions: int) -> None:
        self._max_sessions = max_sessions
        self._proxy: ProxyConfig | None = None
        self._proxy_id: int | None = None
        self._issued_count = 0

    @property
    def proxy_id(self) -> int | None:
        """Id прокси, выданного последним `acquire()`."""
        return self._proxy_id

    async def acquire(self) -> ProxyConfig | None:
        if self._proxy is None or self._issued_count >= self._max_sessions:
            new_proxy = await get_proxy()
            if new_proxy is None:
                return None
            self._proxy = new_proxy.config
            self._proxy_id = new_proxy.proxy_id
            self._issued_count = 0
            logger.info('[proxy_rotate] acquired new proxy host=%s', new_proxy.config.host)
        self._issued_count += 1
        return self._proxy
