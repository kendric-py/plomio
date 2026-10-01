from datetime import datetime

from pydantic import BaseModel, Field

from apps.api.src.routers.schema import PaginationMeta
from packages.user.src.enums import UserRole


class UserResponse(BaseModel):
    id: int = Field(description='Идентификатор пользователя')
    display_name: str = Field(description='Отображаемое имя')
    email: str = Field(description='Email пользователя')
    role: UserRole = Field(description='Роль пользователя')
    telegram_id: int | None = Field(description='Telegram ID пользователя')
    last_active_at: datetime = Field(description='Время последней активности')
    created_at: datetime = Field(description='Время создания')


class CreateUserRequest(BaseModel):
    email: str = Field(min_length=3, description='Email пользователя')
    password: str = Field(min_length=8, description='Пароль в открытом виде')
    display_name: str | None = Field(
        default=None, min_length=1, description='Отображаемое имя (по умолчанию — email)',
    )
    role: UserRole = Field(default=UserRole.CLIENT, description='Роль пользователя')
    credits: int | None = Field(
        default=None,
        ge=0,
        description='Начальное количество кредитов (0 — без кредитов); '
        'не указано — обычный бонус за регистрацию',
    )


class UpdateUserRequest(BaseModel):
    """Частичное обновление: меняются только переданные поля. Очистить `telegram_id` через эту
    ручку нельзя (`null` означает «не менять»)."""

    display_name: str | None = Field(default=None, min_length=1, description='Отображаемое имя')
    email: str | None = Field(default=None, min_length=3, description='Email пользователя')
    role: UserRole | None = Field(default=None, description='Роль пользователя')
    telegram_id: int | None = Field(default=None, description='Telegram ID пользователя')


class UserListResponse(BaseModel):
    items: list[UserResponse] = Field(description='Пользователи на странице')
    meta: PaginationMeta
