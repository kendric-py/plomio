from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ApiKeyEntity(BaseModel):
    id: Optional[int] = Field(default=None, description='Идентификатор ключа')
    user_id: Optional[int] = Field(default=None, description='Владелец ключа')
    name: Optional[str] = Field(default=None, description='Название, которое дал пользователь')
    prefix: Optional[str] = Field(default=None, description='Первые символы ключа для отображения')
    key_hash: Optional[str] = Field(default=None, description='SHA-256 значения ключа')
    credit_limit: Optional[int] = Field(
        default=None, description='Лимит трат за всё время жизни ключа; None — без лимита',
    )
    expires_at: Optional[datetime] = Field(
        default=None, description='Когда ключ перестаёт действовать; None — бессрочный',
    )
    revoked_at: Optional[datetime] = Field(default=None, description='Когда ключ отозван')
    last_used_at: Optional[datetime] = Field(
        default=None, description='Последняя авторизация ключом (с точностью до минуты)',
    )
    created_at: Optional[datetime] = Field(default=None, description='Время создания')
    updated_at: Optional[datetime] = Field(default=None, description='Время изменения')


class ApiKeyWithSpendingEntity(ApiKeyEntity):
    """Ключ вместе с тем, сколько кредитов по нему потрачено (по журналу `credit_transactions`)."""

    spent_credits: int = Field(default=0, description='Потрачено кредитов за всё время')


class ApiKeyUpdateData(BaseModel):
    """Изменения ключа. Применяются только поля, переданные явно (`model_fields_set`): так `None`
    у `credit_limit`/`expires_at` означает «снять лимит/срок», а не «не менять»."""

    name: Optional[str] = Field(default=None, description='Новое название')
    credit_limit: Optional[int] = Field(default=None, description='Новый лимит; None — без лимита')
    expires_at: Optional[datetime] = Field(
        default=None, description='Новый срок; None — бессрочный',
    )
