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
