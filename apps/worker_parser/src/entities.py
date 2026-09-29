from typing import Generic, TypeVar

from pydantic import BaseModel, Field

from core.enums import Marketplace

# `SessionMessage` живёт в packages/sessions (общий Redis-контракт с apps/worker_sessions, см.
# packages/sessions/AGENTS.md); реэкспорт — чтобы модули воркера импортировали его отсюда.
from packages.sessions.src.entities import SessionMessage  # noqa: F401


class OzonPaginationCursor(BaseModel):
    marketplace: Marketplace = Field(...)
    next_url: str | None = Field(...)
    referer: str = Field(...)
    prev_request_id: str | None = Field(default=None)


class OzonReviewCursor(BaseModel):
    """Курсор отзывов Ozon: `next_params` — query-строка следующей страницы прямо из
    `paging.nextButton` (содержит `page_key` Ozon). Без `page_key` глубже ~5-й страницы Ozon
    повторяет уже выданные отзывы, поэтому голый номер страницы курсором быть не может."""

    marketplace: Marketplace = Field(...)
    sort_order: str = Field(..., description='Текущая сортировка (обход нескольких — режим задач)')
    next_params: str | None = Field(
        default=None, description='Query-строка следующей страницы; None — начало сортировки',
    )
    seen_uuids: list[str] = Field(default_factory=list)


class WildberriesPaginationCursor(BaseModel):
    marketplace: Marketplace = Field(...)
    page_num: int = Field(...)
    total_on_site: int | None = Field(default=None)
    collected_so_far: int | None = Field(default=None)


class WbReviewCursor(BaseModel):
    """WB отдаёт все отзывы одним ответом, поэтому страница — срез `[offset:offset+page_size]`;
    `root_id`/`feedback_host` кэшируются в курсоре, чтобы следующие страницы обходились без
    прогрева и определения хоста — одним запросом."""

    marketplace: Marketplace = Field(...)
    offset: int = Field(..., ge=0)
    root_id: int = Field(...)
    feedback_host: str = Field(...)


Cursor = OzonPaginationCursor | OzonReviewCursor | WildberriesPaginationCursor | WbReviewCursor

ItemT = TypeVar('ItemT', bound=BaseModel)


class Page(BaseModel, Generic[ItemT]):
    """Результат одного вызова `fetch_page`. Карточка товара — страница с `next_cursor=None`."""

    items: list[ItemT] = Field(default_factory=list)
    next_cursor: Cursor | None = Field(default=None)
