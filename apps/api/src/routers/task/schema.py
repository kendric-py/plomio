from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from core.enums import Marketplace
from packages.task.src.enums import ParseType, TaskStatus


class CreateTaskRequest(BaseModel):
    parse_type: ParseType = Field(description='Тип парсинга')
    marketplace: Marketplace = Field(description='Маркетплейс задачи')
    inputs: list[str] = Field(
        description='Список входов задачи: ссылок или поисковых запросов',
        min_length=1,
    )
    priority: int = Field(default=5, description='Приоритет от 1 (высший) до 10', ge=1, le=10)
    ttl_seconds: int = Field(
        description='Через сколько секунд задача считается просроченной, если не взята в работу',
        gt=0,
    )
    result_limit: int | None = Field(default=None, description='Общий лимит результатов по задаче')


class TaskResponse(BaseModel):
    id: UUID = Field(description='Идентификатор задачи')
    parse_type: ParseType = Field(description='Тип парсинга')
    marketplace: Marketplace = Field(description='Маркетплейс задачи')
    status: TaskStatus = Field(description='Статус задачи')
    priority: int = Field(description='Приоритет от 1 (высший) до 10')
    queue_expires_at: datetime = Field(
        description='Момент, до которого задача должна быть взята в работу',
    )
    result_limit: int | None = Field(description='Общий лимит результатов по задаче')
    user_id: int = Field(description='Идентификатор пользователя, поставившего задачу')
    created_at: datetime = Field(description='Время создания задачи')


class ResultItemResponse(BaseModel):
    id: UUID = Field(description='Идентификатор строки результата')
    task_item_id: UUID = Field(description='Идентификатор элемента задачи-источника')
    marketplace: Marketplace = Field(description='Маркетплейс сущности')
    parse_type: ParseType = Field(description='Тип парсинга, породивший эту сущность')
    payload: dict = Field(description='Спарсенная сущность (товар/карточка/отзыв/профиль продавца)')
    created_at: datetime = Field(description='Время сохранения сущности')


class PaginationMeta(BaseModel):
    total: int = Field(description='Общее количество элементов')
    limit: int = Field(description='Размер страницы')
    offset: int = Field(description='Смещение страницы')


class TaskResultsResponse(BaseModel):
    items: list[ResultItemResponse] = Field(description='Результаты задачи на текущей странице')
    meta: PaginationMeta = Field(description='Метаданные пагинации')


class TaskListItemResponse(TaskResponse):
    error_reason: str | None = Field(description='Причина общего провала задачи')
    total_items: int = Field(description='Общее количество входов задачи')
    processed_items: int = Field(
        description='Количество входов, доведённых до терминального статуса',
    )
    result_count: int = Field(description='Суммарное количество спарсенных результатов')


class TaskListResponse(BaseModel):
    items: list[TaskListItemResponse] = Field(description='Задачи пользователя на текущей странице')
    meta: PaginationMeta = Field(description='Метаданные пагинации')


class TaskStatusResponse(BaseModel):
    id: UUID = Field(description='Идентификатор задачи')
    parse_type: ParseType = Field(description='Тип парсинга')
    marketplace: Marketplace = Field(description='Маркетплейс задачи')
    status: TaskStatus = Field(description='Статус задачи')
    error_reason: str | None = Field(description='Причина общего провала задачи')
    total_items: int = Field(description='Общее количество входов задачи')
    processed_items: int = Field(
        description='Количество входов, доведённых до терминального статуса',
    )
    result_count: int = Field(description='Суммарное количество спарсенных результатов')
    created_at: datetime = Field(description='Время создания задачи')
