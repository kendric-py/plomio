from datetime import datetime

from pydantic import BaseModel, Field

from packages.user.src.enums import UserRole


class UserResponse(BaseModel):
    id: int = Field(description='Идентификатор пользователя')
    display_name: str = Field(description='Отображаемое имя')
    email: str = Field(description='Email пользователя')
    role: UserRole = Field(description='Роль пользователя')
    telegram_id: int | None = Field(description='Telegram ID пользователя')
    last_active_at: datetime = Field(description='Время последней активности')
    created_at: datetime = Field(description='Время создания')
