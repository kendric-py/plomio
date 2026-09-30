from datetime import datetime

from pydantic import BaseModel, Field

# Общие REST-примитивы, переиспользуемые несколькими роутерами (не привязаны к домену конкретного
# роутера — в отличие от схем в `routers/<domain>/schema.py`).


class PaginationMeta(BaseModel):
    """Метаданные пагинации. Используется как последнее поле (`meta`) в любом постраничном
    REST-ответе — сейчас в `TaskListResponse`/`TaskResultsResponse` (`routers/task/schema.py`) и
    `AutomationListResponse`/`AutomationHistoryListResponse` (`routers/automation/schema.py`)."""

    total: int = Field(description='Общее количество элементов')
    limit: int = Field(description='Размер страницы')
    offset: int = Field(description='Смещение страницы')


class DateRange(BaseModel):
    """Опциональный фильтр по периоду дат (UTC, границы включительные). Создаётся зависимостью
    `get_date_range` (`routers/dependencies.py`); сейчас используется в `GET /api/tasks/`
    (`routers/task/endpoints.py`). Какую именно колонку времени фильтровать, решает домен."""

    date_from: datetime | None = Field(default=None, description='Начало периода (включительно)')
    date_to: datetime | None = Field(default=None, description='Конец периода (включительно)')
