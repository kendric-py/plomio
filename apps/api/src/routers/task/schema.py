from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from apps.api.src.routers.schema import PaginationMeta
from core.enums import Marketplace
from packages.task.src.enums import ParseType, TaskItemStatus, TaskStatus

# --- Переиспользуемые сущности ---
# Общие строительные блоки схем запросов/ответов ниже. Любое поле задачи/её прогресса описывается
# здесь один раз, чтобы одинаковые по смыслу ручки (создание, список, статус) не расходились
# составом полей.


class TaskItemResponse(BaseModel):
    """Один вход задачи (`TaskItem`). Вложен в `CreateTaskResponse.items` (`POST /api/tasks/`)."""

    id: UUID = Field(description='Идентификатор элемента задачи')
    position: int = Field(description='Порядковый номер входа в задаче')
    input_value: str = Field(description='Ссылка или поисковый запрос')
    status: TaskItemStatus = Field(description='Статус элемента задачи')


class TaskBaseResponse(BaseModel):
    """Общие поля задачи. Сам по себе не используется как ответ ручки — база для
    `CreateTaskResponse` (`POST /api/tasks/`) и `TaskDetailResponse`
    (`GET /api/tasks/`, `GET /api/tasks/{task_id}`)."""

    id: UUID = Field(description='Идентификатор задачи')
    parse_type: ParseType = Field(description='Тип парсинга')
    marketplace: Marketplace = Field(description='Маркетплейс задачи')
    status: TaskStatus = Field(description='Статус задачи')
    priority: int = Field(description='Приоритет от 1 (высший) до 10')
    queue_expires_at: datetime = Field(
        description='Момент, до которого задача должна быть взята в работу',
    )
    result_limit: int | None = Field(description='Лимит результатов на каждый вход задачи (не на задачу целиком)')
    error_reason: str | None = Field(description='Причина общего провала задачи')
    user_id: int = Field(description='Идентификатор пользователя, поставившего задачу')
    automation_id: UUID | None = Field(
        description='Идентификатор автоматизации, создавшей эту задачу (проверочная задача, не '
        'пользовательская)',
    )
    pricing_dimension_code: str | None = Field(
        description='Код измерения billing-множителя, применённого к результатам этой задачи',
    )
    pricing_dimension_value: int | None = Field(
        description='Значение измерения billing-множителя на момент создания задачи',
    )
    started_at: datetime | None = Field(
        description='Момент начала парсинга (первый захват задачи воркером); `null`, если задача '
        'ещё не была взята в работу',
    )
    finished_at: datetime | None = Field(
        description='Момент завершения парсинга (успех/провал/отмена); `null`, если задача ещё не '
        'завершена. Вместе с started_at позволяет посчитать длительность парсинга',
    )
    created_at: datetime = Field(description='Время создания задачи')
    updated_at: datetime = Field(description='Время последнего изменения задачи')


class TaskProgressFields(BaseModel):
    """Агрегированный прогресс задачи. Сам по себе не используется как ответ ручки — база для
    `TaskDetailResponse` (`GET /api/tasks/`, `GET /api/tasks/{task_id}`)."""

    total_items: int = Field(description='Общее количество входов задачи')
    processed_items: int = Field(
        description='Количество входов, доведённых до терминального статуса',
    )
    result_count: int = Field(description='Суммарное количество спарсенных результатов')


class ResultItemResponse(BaseModel):
    """Одна спарсенная сущность. Вложен в `TaskResultsResponse.items`
    (`GET /api/tasks/{task_id}/results`)."""

    id: UUID = Field(description='Идентификатор строки результата')
    task_item_id: UUID = Field(description='Идентификатор элемента задачи-источника')
    marketplace: Marketplace = Field(description='Маркетплейс сущности')
    parse_type: ParseType = Field(description='Тип парсинга, породивший эту сущность')
    payload: dict = Field(description='Спарсенная сущность (товар/карточка/отзыв/профиль продавца)')
    created_at: datetime = Field(description='Время сохранения сущности')


# --- Запросы ---


class CreateTaskRequest(BaseModel):
    """Тело запроса `POST /api/tasks/` — постановка новой задачи парсинга."""

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
    result_limit: int | None = Field(default=None, description='Лимит результатов на каждый вход задачи (не на задачу целиком)')


class ResumeTaskRequest(BaseModel):
    """Тело запроса `POST /api/tasks/{task_id}/resume` — возобновление приостановленной задачи."""

    ttl_seconds: int = Field(
        description='Через сколько секунд задача считается просроченной, если не взята в работу '
        'повторно; отсчитывается заново от момента возобновления (симметрично '
        'CreateTaskRequest.ttl_seconds)',
        gt=0,
    )


# --- Ответы ---


class CreateTaskResponse(TaskBaseResponse):
    """Ответ `POST /api/tasks/` — созданная задача со всеми полями и входами (`items`), которые
    роутер получает через `TaskService.get_task_items` сразу после создания."""

    items: list[TaskItemResponse] = Field(description='Входы задачи, созданные при постановке')


class TaskDetailResponse(TaskProgressFields, TaskBaseResponse):
    """Задача с агрегированным прогрессом. Используется как элемент списка
    в `TaskListResponse.items` (`GET /api/tasks/`) и напрямую как ответ `GET /api/tasks/{task_id}` —
    намеренно один и тот же класс, чтобы состав полей не расходился между этими похожими по смыслу
    ручками."""


class TaskListResponse(BaseModel):
    """Ответ `GET /api/tasks/` — постраничный список задач пользователя."""

    items: list[TaskDetailResponse] = Field(description='Задачи пользователя на текущей странице')
    meta: PaginationMeta = Field(description='Метаданные пагинации')


class TaskResultsResponse(BaseModel):
    """Ответ `GET /api/tasks/{task_id}/results` — постраничные результаты парсинга задачи."""

    items: list[ResultItemResponse] = Field(description='Результаты задачи на текущей странице')
    meta: PaginationMeta = Field(description='Метаданные пагинации')
