from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator

from packages.api_keys.src.enums import ApiKeyStatus


def _as_utc(value: datetime | None) -> datetime | None:
    """Naive datetime трактуется как UTC (как в `get_date_range`)."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


# --- переиспользуемые сущности


class ApiKeyResponse(BaseModel):
    """API-ключ без значения (значение отдаётся только при создании) — элемент `GET /api/api-keys/`,
    ответ `GET`/`PATCH /api/api-keys/{id}` и `POST /api/api-keys/{id}/revoke`; база
    `CreateApiKeyResponse`."""

    id: int = Field(description='Идентификатор ключа')
    name: str = Field(description='Название ключа')
    prefix: str = Field(description='Первые символы ключа — чтобы узнать его в списке')
    status: ApiKeyStatus = Field(description='ACTIVE / EXPIRED / REVOKED')
    credit_limit: int | None = Field(description='Лимит трат за всё время; null — без лимита')
    spent_credits: int = Field(description='Потрачено кредитов через этот ключ за всё время')
    remaining_credits: int | None = Field(
        description='Осталось до лимита (не меньше 0); null — без лимита',
    )
    expires_at: datetime | None = Field(description='Срок действия; null — бессрочный')
    revoked_at: datetime | None = Field(description='Когда ключ отозван')
    last_used_at: datetime | None = Field(
        description='Последний запрос с ключом (с точностью до минуты)',
    )
    created_at: datetime = Field(description='Время создания')


# --- запросы


class CreateApiKeyRequest(BaseModel):
    """Тело `POST /api/api-keys/`."""

    name: str = Field(min_length=1, max_length=100, description='Название ключа')
    credit_limit: int | None = Field(
        default=None, ge=1, description='Лимит трат за всё время; null — без лимита',
    )
    expires_at: datetime | None = Field(
        default=None, description='Срок действия (в будущем); null — бессрочный',
    )

    @field_validator('name')
    @classmethod
    def strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError('name must not be blank')
        return stripped

    @field_validator('expires_at')
    @classmethod
    def expires_at_utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value)


class UpdateApiKeyRequest(BaseModel):
    """Тело `PATCH /api/api-keys/{id}`. Меняются только переданные поля; явный `null` у
    `credit_limit`/`expires_at` снимает лимит/срок, `name` в `null` установить нельзя."""

    name: str | None = Field(
        default=None, min_length=1, max_length=100, description='Новое название',
    )
    credit_limit: int | None = Field(
        default=None, ge=1, description='Новый лимит; null — без лимита',
    )
    expires_at: datetime | None = Field(default=None, description='Новый срок; null — бессрочный')

    @field_validator('name')
    @classmethod
    def strip_name(cls, value: str | None) -> str:
        if value is None or not value.strip():
            raise ValueError('name must not be blank')
        return value.strip()

    @field_validator('expires_at')
    @classmethod
    def expires_at_utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value)


# --- ответы


class CreateApiKeyResponse(ApiKeyResponse):
    """Ответ `POST /api/api-keys/`: ключ плюс его значение — показывается один раз, больше его
    узнать нельзя (хранится только хэш)."""

    key: str = Field(description='Значение ключа (plm_...) — сохраните, повторно не показывается')


class ApiKeyListResponse(BaseModel):
    """Ответ `GET /api/api-keys/` — все ключи пользователя, новые сверху (без пагинации: ключей
    у пользователя единицы)."""

    items: list[ApiKeyResponse] = Field(description='Ключи пользователя')
