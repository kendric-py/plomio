import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from curl_cffi.requests import AsyncSession

from apps.worker_parser.src.config import config
from apps.worker_parser.src.entities import Cursor, Page, SessionMessage
from apps.worker_parser.src.exceptions import DeadlineExceededError
from apps.worker_parser.src.http_client import execute_request


@dataclass(frozen=True)
class FetchContext:
    """Всё, что нужно одному вызову `fetch_page`, кроме входа и курсора. Лимит ретраев и дедлайн
    приходят сюда от вызывающего режима (задачи/direct), а не из глобального `.env` — иначе у
    direct с его жёстким дедлайном не было бы способа ограничить время HTTP-запросов."""

    http_session: AsyncSession
    session_message: SessionMessage
    seen_keys: set[str] = field(default_factory=set)
    limit: int | None = None
    http_retries: int = config.HTTP.RETRIES
    # Размер среза для WB-отзывов; None — вернуть все отзывы одной страницей (режим задач).
    review_page_size: int | None = None
    # Ozon-отзывы: обходить все сортировки (режим задач) или одну цепочку страниц (direct).
    walk_all_review_sorts: bool = False
    # Дедлайн в `time.monotonic()`; None — без дедлайна.
    deadline: float | None = None
    # Пустая страница выдачи уже проверена на другой сессии: пустота — конец, а не сбой сессии.
    confirm_empty_page: bool = False

    async def request(self, method: str, url: str, **kwargs: Any) -> Any:
        kwargs['retries'] = min(kwargs.get('retries', self.http_retries), self.http_retries)
        if self.deadline is not None:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise DeadlineExceededError(f'deadline exceeded before request to {url}')
            kwargs['timeout'] = min(kwargs.get('timeout', config.HTTP.TIMEOUT_SECONDS), remaining)
        return await execute_request(self.http_session, method, url, **kwargs)


class PageFetcher(Protocol):
    async def __call__(
        self, input_value: str, cursor: Cursor | None, ctx: FetchContext,
    ) -> Page[Any]: ...
