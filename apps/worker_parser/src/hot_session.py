import asyncio
import logging
import time
from dataclasses import dataclass

from apps.worker_parser.src.config import config
from apps.worker_parser.src.exceptions import BrowserInitError
from apps.worker_parser.src.registry import HTTP_SESSION_FACTORY_BY_MARKETPLACE
from apps.worker_parser.src.session_provider import SessionHandle
from core.enums import Marketplace
from packages.sessions.src.redis_store import SessionPoolStore

logger = logging.getLogger(__name__)

# Как часто перепроверять пул, пока ждём сессию: короче, чем `EMPTY_POOL_BACKOFF_SECONDS` задач,
# потому что у direct всё окно ожидания — секунды.
POOL_RECHECK_SECONDS = 0.2


@dataclass
class _SlotEntry:
    handle: SessionHandle
    acquired_at: float
    users: int = 0
    # Ротация или сбой: выдавать новым запросам нельзя, освободить — когда уйдут текущие.
    retired: bool = False
    # Возвращать ли сессию в пул при освобождении (возраст — да, блокировка/ошибка — нет).
    trusted: bool = True


class HotSessionSlot:
    """`SessionProvider` для direct: одна «горячая» сессия на маркетплейс, которую берём из пула
    один раз и НЕ возвращаем между запросами — следующему не нужно платить за `ZPOPMIN` и новый
    HTTP-клиент, keep-alive соединение живёт. Одна сессия делится между конкурентными запросами
    процесса.

    Ротация: по возрасту (`HOT_SESSION_MAX_AGE_SECONDS`, сессия возвращается в пул) или при
    `discard` (не возвращается). Ротируемую сессию нельзя закрывать под ногами запросов, которые
    её ещё используют, поэтому её освобождение откладывается до ухода последнего."""

    def __init__(self, marketplace: Marketplace, session_client: SessionPoolStore) -> None:
        self._marketplace = marketplace
        self._session_client = session_client
        self._lock = asyncio.Lock()
        self._current: _SlotEntry | None = None
        self._entries: dict[str, _SlotEntry] = {}

    async def warm_up(self) -> None:
        """Прогрев при старте, чтобы первый запрос не платил за получение сессии. Сбой не
        критичен: сессию возьмёт первый запрос."""
        try:
            await self.acquire(deadline=time.monotonic() + config.DIRECT.SESSION_WAIT_SECONDS)
        except BrowserInitError:
            logger.warning('[hot_session_warmup_failed] marketplace=%s', self._marketplace.value)
            return
        await self.release(self._current.handle)

    async def acquire(self, deadline: float | None) -> SessionHandle:
        async with self._lock:
            if self._current is not None and self._is_too_old(self._current):
                self._retire(self._current, trusted=True)
            if self._current is None:
                self._current = await self._take_from_pool(deadline)
            self._current.users += 1
            return self._current.handle

    async def release(self, handle: SessionHandle) -> None:
        entry = self._entries[handle.session_message.session_id]
        entry.users -= 1
        await self._finalize_if_idle(entry)

    async def discard(self, handle: SessionHandle) -> None:
        entry = self._entries[handle.session_message.session_id]
        entry.users -= 1
        self._retire(entry, trusted=False)
        await self._finalize_if_idle(entry)

    async def close(self) -> None:
        for entry in list(self._entries.values()):
            entry.retired = True
            entry.users = 0
            await self._finalize_if_idle(entry)
        self._current = None

    def _is_too_old(self, entry: _SlotEntry) -> bool:
        return time.monotonic() - entry.acquired_at >= config.DIRECT.HOT_SESSION_MAX_AGE_SECONDS

    def _retire(self, entry: _SlotEntry, trusted: bool) -> None:
        entry.retired = True
        entry.trusted = entry.trusted and trusted
        if self._current is entry:
            self._current = None

    async def _finalize_if_idle(self, entry: _SlotEntry) -> None:
        if not entry.retired or entry.users > 0:
            return
        if self._entries.pop(entry.handle.session_message.session_id, None) is None:
            return
        if entry.trusted:
            await self._session_client.release(
                entry.handle.session_message,
                min_ttl_margin_seconds=config.SESSION_POOL.MIN_TTL_MARGIN_SECONDS,
            )
        await entry.handle.http_session.close()

    async def _take_from_pool(self, deadline: float | None) -> _SlotEntry:
        """Порог остаточного TTL — обычный `MIN_TTL_MARGIN_SECONDS`: возраст ротации к нему
        добавлять нельзя, иначе `acquire_session` выбросит из пула все живые сессии (их TTL у
        worker_sessions — 7 минут)."""
        wait_until = time.monotonic() + config.DIRECT.SESSION_WAIT_SECONDS
        if deadline is not None:
            wait_until = min(wait_until, deadline)
        while True:
            session_message = await self._session_client.acquire_session(
                marketplace=self._marketplace,
                max_pop_attempts=config.SESSION_POOL.MAX_POP_ATTEMPTS,
                min_ttl_margin_seconds=config.SESSION_POOL.MIN_TTL_MARGIN_SECONDS,
            )
            if session_message is not None:
                create_http_session = HTTP_SESSION_FACTORY_BY_MARKETPLACE[self._marketplace]
                entry = _SlotEntry(
                    handle=SessionHandle(session_message, create_http_session(session_message)),
                    acquired_at=time.monotonic(),
                )
                self._entries[session_message.session_id] = entry
                return entry
            if time.monotonic() + POOL_RECHECK_SECONDS >= wait_until:
                raise BrowserInitError(f'no {self._marketplace.value} session in the pool')
            await asyncio.sleep(POOL_RECHECK_SECONDS)
