import asyncio
import time
from dataclasses import dataclass
from typing import Protocol

from curl_cffi.requests import AsyncSession

from apps.worker_parser.src.config import config
from apps.worker_parser.src.entities import SessionMessage
from apps.worker_parser.src.enums import WorkerParserStatus
from apps.worker_parser.src.exceptions import BrowserInitError
from apps.worker_parser.src.registry import HTTP_SESSION_FACTORY_BY_MARKETPLACE
from core.enums import Marketplace
from packages.sessions.src.redis_store import SessionPoolStore
from packages.worker_health.src.liveness_reporter import LivenessReporter


@dataclass(frozen=True)
class SessionHandle:
    """Сессия маркетплейса вместе с HTTP-клиентом, построенным из неё: клиент принадлежит
    провайдеру, потому что горячий слот direct держит его между запросами (keep-alive), а пул —
    создаёт и закрывает вместе с выдачей."""

    session_message: SessionMessage
    http_session: AsyncSession


class SessionProvider(Protocol):
    async def acquire(self, deadline: float | None) -> SessionHandle:
        """`deadline` — в `time.monotonic()`; провайдер, который может ждать сессию, обязан
        уложиться в него и выбросить `BrowserInitError`."""
        ...

    async def release(self, handle: SessionHandle) -> None:
        """Сессии всё ещё доверяем — её можно использовать повторно."""
        ...

    async def discard(self, handle: SessionHandle) -> None:
        """Сессия заблокирована или подозрительна — повторно использовать нельзя."""
        ...


class PoolSessionProvider:
    """Режим задач: сессия берётся из общего Redis-пула и возвращается в него, если ей ещё
    доверяем — чтобы неизрасходованный бюджет запросов не пропадал зря."""

    def __init__(
        self,
        marketplace: Marketplace,
        session_client: SessionPoolStore,
        liveness_reporter: LivenessReporter,
    ) -> None:
        self._marketplace = marketplace
        self._session_client = session_client
        self._liveness_reporter = liveness_reporter

    async def acquire(self, deadline: float | None) -> SessionHandle:
        while True:
            session_message = await self._session_client.acquire_session(
                marketplace=self._marketplace,
                max_pop_attempts=config.SESSION_POOL.MAX_POP_ATTEMPTS,
                min_ttl_margin_seconds=config.SESSION_POOL.MIN_TTL_MARGIN_SECONDS,
            )
            if session_message is not None:
                self._liveness_reporter.set_status(WorkerParserStatus.WORKING.value)
                create_http_session = HTTP_SESSION_FACTORY_BY_MARKETPLACE[self._marketplace]
                return SessionHandle(session_message, create_http_session(session_message))
            self._liveness_reporter.set_status(WorkerParserStatus.WAITING_FOR_SESSION.value)
            backoff = config.SESSION_POOL.EMPTY_POOL_BACKOFF_SECONDS
            if deadline is not None:
                backoff = min(backoff, deadline - time.monotonic())
                if backoff <= 0:
                    raise BrowserInitError('no session available before deadline')
            await asyncio.sleep(backoff)

    async def release(self, handle: SessionHandle) -> None:
        await handle.http_session.close()
        await self._session_client.release(
            handle.session_message,
            min_ttl_margin_seconds=config.SESSION_POOL.MIN_TTL_MARGIN_SECONDS,
        )

    async def discard(self, handle: SessionHandle) -> None:
        await handle.http_session.close()
