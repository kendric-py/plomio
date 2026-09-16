from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from packages.user.src.enums import UserRole


class UserEntity(BaseModel):
    id: Optional[int] = Field(default=None, description='Идентификатор пользователя')
    display_name: Optional[str] = Field(default=None, description='Отображаемое имя')
    email: Optional[str] = Field(default=None, description='Email пользователя')
    hashed_password: Optional[str] = Field(default=None, description='Хэш пароля')
    role: Optional[UserRole] = Field(default=None, description='Роль пользователя')
    telegram_id: Optional[int] = Field(default=None, description='Telegram ID пользователя')
    last_active_at: Optional[datetime] = Field(default=None, description='Время последней активности')
    created_at: Optional[datetime] = Field(default=None, description='Время создания')
