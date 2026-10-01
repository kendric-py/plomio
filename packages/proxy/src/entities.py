from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from packages.proxy.src.enums import ProxyType


class ProxyEntity(BaseModel):
    id: Optional[int] = Field(default=None, description='Идентификатор прокси')
    proxy_type: Optional[ProxyType] = Field(default=None, description='Тип прокси: http или socks5')
    host: Optional[str] = Field(default=None, description='Хост прокси')
    port: Optional[int] = Field(default=None, description='Порт прокси')
    username: Optional[str] = Field(
        default=None,
        description='Логин; None — прокси без авторизации',
    )
    password: Optional[str] = Field(default=None, description='Пароль; None — прокси без пароля')
    is_active: Optional[bool] = Field(
        default=None,
        description='Участвует ли прокси в случайной выдаче воркерам',
    )
    note: Optional[str] = Field(default=None, description='Произвольная заметка админа')
    created_at: Optional[datetime] = Field(default=None, description='Время создания')
    updated_at: Optional[datetime] = Field(default=None, description='Время последнего изменения')
