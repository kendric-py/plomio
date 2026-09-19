from pydantic import BaseModel, Field

from core.enums import Marketplace

# `ProxyConfig`/`SessionMessage` moved to packages/sessions (shared Redis wire contract with
# apps/worker_sessions) — see packages/sessions/AGENTS.md. Re-exported here so existing imports of
# `apps.worker_parser.src.entities` keep working unchanged.
from packages.sessions.src.entities import ProxyConfig, SessionMessage  # noqa: F401


class OzonPaginationCursor(BaseModel):
    marketplace: Marketplace = Field(...)
    next_url: str | None = Field(...)
    referer: str = Field(...)
    prev_request_id: str | None = Field(default=None)


class OzonReviewCursor(BaseModel):
    marketplace: Marketplace = Field(...)
    product_path: str = Field(...)
    start_page_id: str = Field(...)
    sort_order: str = Field(...)
    next_url: str | None = Field(default=None)
    referer: str = Field(...)
    prev_request_id: str | None = Field(default=None)
    seen_uuids: list[str] = Field(default_factory=list)


class WildberriesPaginationCursor(BaseModel):
    marketplace: Marketplace = Field(...)
    page_num: int = Field(...)
    total_on_site: int | None = Field(default=None)
    collected_so_far: int | None = Field(default=None)


class WildberriesReviewCursor(BaseModel):
    marketplace: Marketplace = Field(...)
    nm_id: int = Field(...)
    root_id: int | None = Field(default=None)
    feedback_host: str | None = Field(default=None)
