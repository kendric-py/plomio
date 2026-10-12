from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from core.enums import Marketplace
from packages.direct.src.enums import DirectOutcome, DirectRequestType, DirectStatus


class DirectRequest(BaseModel):
    request_id: str = Field(..., description='Идентификатор запроса; ключ списка ответа')
    request_type: DirectRequestType = Field(...)
    marketplace: Marketplace = Field(...)
    input_value: str = Field(..., description='Артикул/ссылка товара или текст поискового запроса')
    page_cursor: dict[str, Any] | None = Field(
        default=None,
        description='Курсор маркетплейса из проверенного page_key; None — 1-я страница',
    )
    created_at: float = Field(..., description='Unix-секунды постановки в очередь')
    # Unix-секунды, а не ISO8601, как остальные даты проекта: воркер сравнивает срок с
    # `time.time()` на каждом запросе, и это осознанное исключение из правила про даты.
    deadline_at: float = Field(..., description='Unix-секунды, после которых ответ не нужен')


class DirectReply(BaseModel):
    request_id: str = Field(...)
    status: DirectStatus = Field(...)
    payload: dict[str, Any] | None = Field(default=None)
    next_cursor: dict[str, Any] | None = Field(default=None)
    # Только для логов: клиенту не отдаётся никогда (см. AGENTS.md, "Ошибки клиенту").
    error: str | None = Field(default=None)
    # Диагностика воркера для истории запросов (`direct_requests`): клиенту не отдаётся. Поля
    # необязательные — воркер старой версии их не присылает.
    attempts: int | None = Field(default=None, description='Попыток к маркетплейсу')
    queue_ms: int | None = Field(default=None, description='От постановки до взятия воркером, мс')
    session_ms: int | None = Field(default=None, description='Получение сессии, мс')
    fetch_ms: int | None = Field(default=None, description='Запросы к маркетплейсу, мс')
    worker_ms: int | None = Field(default=None, description='Весь путь в воркере, мс')
    proxy_id: int | None = Field(default=None, description='Прокси использованной сессии')


class DirectRequestRecordEntity(BaseModel):
    """Строка истории direct-запросов (`direct_requests`); результата запроса в ней нет."""

    id: int | None = Field(default=None, description='Идентификатор записи')
    request_id: str | None = Field(default=None, description='Идентификатор запроса')
    user_id: int | None = Field(default=None, description='Пользователь; None — удалён')
    marketplace: Marketplace | None = Field(default=None, description='Маркетплейс')
    request_type: DirectRequestType | None = Field(default=None, description='Тип запроса')
    outcome: DirectOutcome | None = Field(default=None, description='Итог запроса')
    http_status: int | None = Field(default=None, description='HTTP-статус, отданный клиенту')
    input_value: str | None = Field(default=None, description='Артикул, ссылка или текст запроса')
    is_next_page: bool | None = Field(default=None, description='Запрос не первой страницы')
    items_count: int | None = Field(default=None, description='Сколько элементов вернули')
    has_next_page: bool | None = Field(default=None, description='Есть ли следующая страница')
    credits_charged: int | None = Field(default=None, description='Списано кредитов')
    proxy_id: int | None = Field(default=None, description='Прокси сессии воркера')
    total_ms: int | None = Field(default=None, description='Полное время в API, мс')
    attempts: int | None = Field(default=None, description='Попыток у воркера')
    queue_ms: int | None = Field(default=None, description='Ожидание воркера, мс')
    session_ms: int | None = Field(default=None, description='Получение сессии, мс')
    fetch_ms: int | None = Field(default=None, description='Запросы к маркетплейсу, мс')
    worker_ms: int | None = Field(default=None, description='Весь путь в воркере, мс')
    error_detail: str | None = Field(default=None, description='Внутренняя причина сбоя')
    created_at: datetime | None = Field(default=None, description='Время запроса (UTC)')


class DirectRequestFilters(BaseModel):
    """Фильтры админского списка истории; все необязательные, объединяются через AND."""

    user_id: int | None = Field(default=None, description='Пользователь')
    marketplace: Marketplace | None = Field(default=None, description='Маркетплейс')
    request_type: DirectRequestType | None = Field(default=None, description='Тип запроса')
    outcome: DirectOutcome | None = Field(default=None, description='Итог')
    proxy_id: int | None = Field(default=None, description='Прокси')
    search: str | None = Field(
        default=None, description='Подстрока в запросе или точный `request_id`',
    )
    date_from: datetime | None = Field(default=None, description='Начало периода (включительно)')
    date_to: datetime | None = Field(default=None, description='Конец периода (включительно)')


class DirectSummaryEntity(BaseModel):
    """Агрегат истории за период."""

    total: int = Field(description='Всего запросов')
    by_outcome: dict[DirectOutcome, int] = Field(description='Число запросов по итогам')
    by_type: dict[DirectRequestType, int] = Field(description='Число запросов по типам')
    credits_charged: int = Field(description='Списано кредитов')
    avg_total_ms: int = Field(description='Среднее полное время успешных запросов, мс')
    p95_total_ms: int = Field(description='95-й перцентиль полного времени успешных, мс')
