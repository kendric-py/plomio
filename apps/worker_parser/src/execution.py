import asyncio
import time
from dataclasses import dataclass
from functools import partial
from typing import Awaitable, Callable, TypeVar

from apps.worker_parser.src.config import config
from apps.worker_parser.src.entities import Cursor, Page
from apps.worker_parser.src.error_classifier import ErrorClassification, classify_error
from apps.worker_parser.src.exceptions import (
    DeadlineExceededError,
    EmptyPageUnconfirmedError,
    ParserError,
)
from apps.worker_parser.src.fetch_context import FetchContext
from apps.worker_parser.src.registry import PageOperation
from apps.worker_parser.src.retry_policy import SessionAction
from apps.worker_parser.src.session_provider import SessionHandle, SessionProvider

ResultT = TypeVar('ResultT')


@dataclass(frozen=True)
class ExecutionOptions:
    """Параметры, которыми режимы отличаются друг от друга; всё остальное в цикле общее."""

    # Потолок числа попыток на один вызов; None — решает только политика ретраев (режим задач).
    max_attempts: int | None = None
    # Дедлайн в `time.monotonic()`; None — без дедлайна.
    deadline: float | None = None
    http_retries: int = config.HTTP.RETRIES
    review_page_size: int | None = None
    walk_all_review_sorts: bool = False


@dataclass
class ExecutionStats:
    """Тайминги для лога direct: сколько ушло на получение сессии и на запросы к маркетплейсу
    (суммарно по попыткам)."""

    attempts: int = 0
    session_seconds: float = 0.0
    fetch_seconds: float = 0.0


class FetchFailedError(Exception):
    """Попытки исчерпаны. Несёт исходную ошибку и её классификацию — вызывающий сам решает, что
    с ней делать (завершить элемент задачи или ответить клиенту direct)."""

    def __init__(self, cause: ParserError, classification: ErrorClassification) -> None:
        super().__init__(str(cause))
        self.cause = cause
        self.classification = classification


class PageExecutor:
    """Единый цикл «взять сессию → выполнить → ретрай по политике» для одного элемента задачи или
    одного direct-запроса. Держит текущую сессию между страницами: она возвращается провайдеру
    только в `close()`, а при `REINIT_SESSION` выбрасывается и берётся новая."""

    def __init__(self, provider: SessionProvider, options: ExecutionOptions) -> None:
        self._provider = provider
        self._options = options
        self._handle: SessionHandle | None = None
        self.stats = ExecutionStats()

    async def fetch_page(
        self,
        operation: PageOperation,
        input_value: str,
        cursor: Cursor | None,
        seen_keys: set[str],
        limit: int | None,
    ) -> Page:
        return await self.run(
            partial(operation.fetch_page, input_value, cursor), seen_keys=seen_keys, limit=limit,
        )

    async def run(
        self,
        call: Callable[[FetchContext], Awaitable[ResultT]],
        seen_keys: set[str] | None = None,
        limit: int | None = None,
        retry: bool = True,
    ) -> ResultT:
        """`retry=False` — одна попытка без политики ретраев: сырое `ParserError` уходит
        вызывающему, а сессия считается ненадёжной (как у профиля продавца — неизвестно, умерла
        сессия или данные просто странные)."""
        attempt_count = 0
        empty_page_seen = False
        while True:
            try:
                handle = await self._ensure_handle()
                context = self._build_context(handle, seen_keys, limit, empty_page_seen)
                return await self._timed_call(call, context)
            except ParserError as error:
                if not retry:
                    await self.discard_session()
                    raise
                classification = classify_error(error)
                attempt_count += 1
                empty_page_seen = empty_page_seen or isinstance(error, EmptyPageUnconfirmedError)
                if classification.policy.session_action == SessionAction.REINIT_SESSION:
                    await self.discard_session()
                if self._is_exhausted(attempt_count, classification):
                    raise FetchFailedError(error, classification) from error

    def _build_context(
        self,
        handle: SessionHandle,
        seen_keys: set[str] | None,
        limit: int | None,
        confirm_empty_page: bool,
    ) -> FetchContext:
        return FetchContext(
            http_session=handle.http_session,
            session_message=handle.session_message,
            seen_keys=seen_keys if seen_keys is not None else set(),
            limit=limit,
            http_retries=self._options.http_retries,
            review_page_size=self._options.review_page_size,
            walk_all_review_sorts=self._options.walk_all_review_sorts,
            deadline=self._options.deadline,
            confirm_empty_page=confirm_empty_page,
        )

    async def _timed_call(
        self,
        call: Callable[[FetchContext], Awaitable[ResultT]],
        context: FetchContext,
    ) -> ResultT:
        self.stats.attempts += 1
        started = time.monotonic()
        try:
            return await self._call_within_deadline(call, context)
        finally:
            self.stats.fetch_seconds += time.monotonic() - started

    async def discard_session(self) -> None:
        if self._handle is not None:
            await self._provider.discard(self._handle)
            self._handle = None

    async def close(self) -> None:
        """Вернуть сессию, если ей ещё доверяем. Вызывать в `finally` вызывающего кода."""
        if self._handle is not None:
            await self._provider.release(self._handle)
            self._handle = None

    def _is_exhausted(self, attempt_count: int, classification: ErrorClassification) -> bool:
        if attempt_count > classification.policy.max_attempts:
            return True
        cap = self._options.max_attempts
        return cap is not None and attempt_count >= cap

    async def _ensure_handle(self) -> SessionHandle:
        if self._handle is None:
            started = time.monotonic()
            try:
                self._handle = await self._provider.acquire(self._options.deadline)
            finally:
                self.stats.session_seconds += time.monotonic() - started
        return self._handle

    async def _call_within_deadline(
        self,
        call: Callable[[FetchContext], Awaitable[ResultT]],
        context: FetchContext,
    ) -> ResultT:
        deadline = self._options.deadline
        if deadline is None:
            return await call(context)
        remaining = deadline - time.monotonic()
        try:
            return await asyncio.wait_for(call(context), timeout=max(remaining, 0))
        except asyncio.TimeoutError as error:
            raise DeadlineExceededError('deadline exceeded') from error
