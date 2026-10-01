import uuid
from datetime import datetime, timezone

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

    def to_curl_url(self) -> str:
        """URL для curl_cffi/libcurl. Для SOCKS5 — `socks5h://`: при `socks5://` libcurl резолвит
        DNS локально и отдаёт прокси голый IP. У хостов с AAAA-записью (www.wildberries.ru) это
        IPv6, который сеть прокси не маршрутизирует, — ошибка `curl: (97) cannot complete SOCKS5
        connection ... (3)` на каждом запросе. `socks5h://` отдаёт прокси имя хоста, и он резолвит
        его сам. Браузерная сторона (`to_url`) так же передаёт имя хоста через свой локальный
        SOCKS5-туннель."""
        url = self.to_url()
        return 'socks5h://' + url.removeprefix('socks5://') if url.startswith('socks5://') else url


class SessionMessage(BaseModel):
    session_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    marketplace: Marketplace = Field(...)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # None only when generated with GENERATION_REQUIRE_PROXY=false (local dev without a proxy
    # API yet) — a direct connection was used instead of an upstream proxy.
    proxy: ProxyConfig | None = Field(default=None)
    cookies: dict[str, str] = Field(...)
    user_agent: str = Field(...)
    sec_ch_ua: str = Field(...)
    sec_ch_ua_platform: str = Field(...)
    extra: dict[str, str] = Field(default_factory=dict)
