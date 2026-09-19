import time
import uuid

from pydantic import BaseModel, Field

from core.enums import Marketplace


class ProxyConfig(BaseModel):
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
    session_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    marketplace: Marketplace = Field(...)
    created_at: float = Field(default_factory=time.time)
    # None only when generated with GENERATION_REQUIRE_PROXY=false (local dev without a proxy
    # API yet) — a direct connection was used instead of an upstream proxy.
    proxy: ProxyConfig | None = Field(default=None)
    cookies: dict[str, str] = Field(...)
    user_agent: str = Field(...)
    sec_ch_ua: str = Field(...)
    sec_ch_ua_platform: str = Field(...)
    extra: dict[str, str] = Field(default_factory=dict)
