from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field

from core.enums import Marketplace
from packages.proxy.src.enums import ProxyType
from packages.sessions.src.enums import SessionGenerationOutcome


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


class SessionGenerationEntity(BaseModel):
    id: Optional[int] = Field(default=None, description='Идентификатор записи')
    proxy_id: Optional[int] = Field(
        default=None, description='Прокси, через который шла генерация; None — без прокси',
    )
    marketplace: Optional[Marketplace] = Field(default=None, description='Маркетплейс')
    outcome: Optional[SessionGenerationOutcome] = Field(
        default=None, description='Итог генерации: успех или тип ошибки',
    )
    traceback: Optional[str] = Field(
        default=None, description='Оригинальная ошибка (трейсбек) для анализа',
    )
    created_at: Optional[datetime] = Field(default=None, description='Время генерации (UTC)')


class OutcomeCount(BaseModel):
    outcome: SessionGenerationOutcome = Field(description='Итог генерации')
    count: int = Field(description='Сколько раз встретился за период')


class ProxyGenerationRate(BaseModel):
    proxy_id: int = Field(description='Идентификатор прокси')
    success: int = Field(description='Успешных генераций за период')
    total: int = Field(description='Всего генераций за период (без антибот-ошибок)')


class OutcomeDayCount(BaseModel):
    day: date = Field(description='День (UTC)')
    outcome: SessionGenerationOutcome = Field(description='Итог генерации')
    count: int = Field(description='Сколько раз встретился за день')
