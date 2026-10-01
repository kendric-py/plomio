from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from apps.api.src.routers.schema import PaginationMeta
from packages.proxy.src.enums import ProxyType

# --- Админские ручки (`/api/admin/proxies`) ---


def _strip_non_empty(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError('must not be blank')
    return stripped


class ProxyResponse(BaseModel):
    """Прокси в админском списке/ответах на создание и правку. Пароль наружу не отдаётся —
    только признак `has_password`."""

    id: int = Field(description='Идентификатор прокси')
    proxy_type: ProxyType = Field(description='Тип прокси: http или socks5')
    host: str = Field(description='Хост прокси')
    port: int = Field(description='Порт прокси')
    username: str | None = Field(description='Логин; null — прокси без авторизации')
    has_password: bool = Field(description='Задан ли пароль (сам пароль не возвращается)')
    is_active: bool = Field(description='Участвует ли прокси в случайной выдаче воркерам')
    note: str | None = Field(description='Произвольная заметка админа')
    created_at: datetime = Field(description='Время создания')
    updated_at: datetime = Field(description='Время последнего изменения')


class ProxyListResponse(BaseModel):
    items: list[ProxyResponse] = Field(description='Прокси текущей страницы')
    meta: PaginationMeta = Field(description='Метаданные пагинации')


class CreateProxyRequest(BaseModel):
    proxy_type: ProxyType = Field(description='Тип прокси: http или socks5')
    host: str = Field(description='Хост прокси')
    port: int = Field(ge=1, le=65535, description='Порт прокси')
    username: str | None = Field(default=None, description='Логин (если прокси с авторизацией)')
    password: str | None = Field(default=None, description='Пароль (если прокси с авторизацией)')
    is_active: bool = Field(default=True, description='Участвует ли в выдаче сразу после создания')
    note: str | None = Field(default=None, description='Произвольная заметка')

    @field_validator('host')
    @classmethod
    def _validate_host(cls, value: str) -> str:
        return _strip_non_empty(value)


class UpdateProxyRequest(BaseModel):
    """Частичное обновление: меняются только переданные поля. `username`/`password`/`note`
    можно сбросить, передав `null`."""

    proxy_type: ProxyType | None = Field(default=None, description='Новый тип прокси')
    host: str | None = Field(default=None, description='Новый хост')
    port: int | None = Field(default=None, ge=1, le=65535, description='Новый порт')
    username: str | None = Field(default=None, description='Новый логин; null — сбросить')
    password: str | None = Field(default=None, description='Новый пароль; null — сбросить')
    is_active: bool | None = Field(default=None, description='Включить/выключить из выдачи')
    note: str | None = Field(default=None, description='Новая заметка; null — сбросить')

    @field_validator('host')
    @classmethod
    def _validate_host(cls, value: str | None) -> str | None:
        return None if value is None else _strip_non_empty(value)

    @field_validator('proxy_type', 'host', 'port', 'is_active')
    @classmethod
    def _reject_null(cls, value: object) -> object:
        # Эти колонки NOT NULL: явный `null` в теле — ошибка валидации, а не 500 из БД.
        if value is None:
            raise ValueError('must not be null')
        return value

    def changed_fields(self) -> dict:
        """Только реально переданные поля (в том числе `null` для сбрасываемых)."""
        return {name: getattr(self, name) for name in self.model_fields_set}


# --- Ручка для воркера (`GET /api/proxy/issue`) ---


class IssuedProxyResponse(BaseModel):
    """Формат, который читает `worker_sessions` (`apps/worker_sessions/src/proxy/client.py`)."""

    proxy_type: str = Field(description='Тип прокси: http или socks5')
    proxy_host: str = Field(description='Хост прокси')
    proxy_port: int = Field(description='Порт прокси')
    proxy_username: str | None = Field(description='Логин; null — без авторизации')
    proxy_password: str | None = Field(description='Пароль; null — без пароля')
