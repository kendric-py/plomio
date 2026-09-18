import time
import uuid

from pydantic import BaseModel, Field

from core.enums import Marketplace


class ProxyConfig(BaseModel):
    """Intentional wire-contract duplicate of worker_sessions.entities.ProxyConfig — apps/* do
    not import each other's src/, only core/packages, so the two copies must stay in sync by
    hand if the wire format on RedisSessionStore.save changes. See apps/worker_parser/AGENTS.md."""

    type: str = Field(...)  # "http" | "socks5"
    host: str = Field(...)
    port: int = Field(...)
    username: str | None = Field(default=None)
    password: str | None = Field(default=None)

    def to_url(self) -> str:
        scheme = 'socks5' if self.type == 'socks5' else 'http'
        auth = f'{self.username}:{self.password}@' if self.username and self.password else ''
        return f'{scheme}://{auth}{self.host}:{self.port}'


class SessionMessage(BaseModel):
    """Intentional wire-contract duplicate of worker_sessions.entities.SessionMessage — see
    ProxyConfig above for why this isn't a cross-app import."""

    session_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    marketplace: Marketplace = Field(...)
    created_at: float = Field(default_factory=time.time)
    proxy: ProxyConfig | None = Field(default=None)
    cookies: dict[str, str] = Field(...)
    user_agent: str = Field(...)
    sec_ch_ua: str = Field(...)
    sec_ch_ua_platform: str = Field(...)
    extra: dict[str, str] = Field(default_factory=dict)


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
