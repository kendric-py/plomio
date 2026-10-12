from datetime import datetime

from pydantic import BaseModel, Field

from apps.api.src.routers.schema import PaginationMeta
from core.enums import Marketplace
from packages.direct.src.enums import DirectOutcome, DirectRequestType


# --- Переиспользуемые сущности


class DirectOutcomeCount(BaseModel):
    outcome: DirectOutcome = Field(description='Итог запроса')
    count: int = Field(description='Число запросов с этим итогом')


class DirectTypeCount(BaseModel):
    request_type: DirectRequestType = Field(description='Тип запроса')
    count: int = Field(description='Число запросов этого типа')


class DirectRequestResponse(BaseModel):
    """Одна запись истории direct-запросов. Результата запроса (товары, отзывы) здесь нет."""

    id: int = Field(description='Идентификатор записи')
    request_id: str = Field(description='Идентификатор запроса (как в логах и журнале кредитов)')
    user_id: int | None = Field(description='Пользователь; `null`, если его удалили')
    marketplace: Marketplace = Field(description='Маркетплейс')
    request_type: DirectRequestType = Field(description='Тип запроса')
    outcome: DirectOutcome = Field(description='Итог запроса')
    http_status: int = Field(description='HTTP-статус, отданный клиенту')
    input_value: str = Field(description='Артикул, ссылка или текст запроса (до 500 символов)')
    is_next_page: bool = Field(description='Запрос не первой страницы')
    items_count: int | None = Field(description='Сколько элементов вернули')
    has_next_page: bool | None = Field(description='Есть ли следующая страница')
    credits_charged: int = Field(description='Списано кредитов')
    proxy_id: int | None = Field(description='Прокси сессии воркера, если известен')
    total_ms: int = Field(description='Полное время в API, мс')
    attempts: int | None = Field(description='Попыток к маркетплейсу')
    queue_ms: int | None = Field(description='Ожидание воркера, мс')
    session_ms: int | None = Field(description='Получение сессии, мс')
    fetch_ms: int | None = Field(description='Запросы к маркетплейсу, мс')
    worker_ms: int | None = Field(description='Весь путь в воркере, мс')
    error_detail: str | None = Field(description='Внутренняя причина сбоя (только для админа)')
    created_at: datetime = Field(description='Время запроса (UTC)')


# --- Ответы


class DirectRequestListResponse(BaseModel):
    """Ответ `GET /api/admin/direct-requests/` — история direct-запросов, новые сверху."""

    items: list[DirectRequestResponse] = Field(description='Записи на странице')
    meta: PaginationMeta = Field(description='Метаданные пагинации')


class DirectSummaryResponse(BaseModel):
    """Ответ `GET /api/admin/direct-requests/summary` — агрегат по тем же фильтрам, что у списка."""

    total: int = Field(description='Всего запросов')
    success_percent: int = Field(description='Доля успешных, %; 0, если запросов не было')
    by_outcome: list[DirectOutcomeCount] = Field(description='Запросы по итогам, частые первыми')
    by_type: list[DirectTypeCount] = Field(description='Запросы по типам, частые первыми')
    credits_charged: int = Field(description='Списано кредитов')
    avg_total_ms: int = Field(description='Среднее полное время успешных запросов, мс')
    p95_total_ms: int = Field(description='95-й перцентиль полного времени успешных, мс')
