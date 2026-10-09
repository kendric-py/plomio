from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from apps.api.src.routers.schema import PaginationMeta
from apps.api.src.routers.task.schema import TaskDetailResponse
from packages.notifications.src.enums import NotificationChannel, NotificationDeliveryStatus
from packages.task.src.enums import TaskItemStatus


class AdminTaskItemResponse(BaseModel):
    """Элемент задачи со всей диагностикой (в отличие от пользовательского `TaskItemResponse`)."""

    id: UUID = Field(description='Идентификатор элемента задачи')
    task_id: UUID = Field(description='Идентификатор родительской задачи')
    position: int = Field(description='Порядковый номер входа в задаче')
    input_value: str = Field(description='Ссылка или поисковый запрос')
    status: TaskItemStatus = Field(description='Статус элемента задачи')
    cursor: dict | None = Field(description='Состояние возобновления пагинации')
    result_count: int = Field(description='Количество спарсенных результатов')
    error_reason: str | None = Field(description='Причина провала элемента')
    created_at: datetime = Field(description='Время создания элемента')
    updated_at: datetime = Field(description='Время последнего изменения элемента')


class AdminTaskNotificationResponse(BaseModel):
    """Уведомление, порождённое задачей: куда, в каком статусе и почему."""

    id: int = Field(description='Идентификатор доставки')
    event_code: str = Field(
        description='Что вызвало уведомление: `task.completed`, `task.failed` или '
        '`automation.change_detected` (изменение карточки/пробитие порога проверкой автоматизации)',
    )
    channel: NotificationChannel = Field(description='Канал доставки')
    status: NotificationDeliveryStatus = Field(
        description='PENDING — в очереди на отправку, SENT — отправлено, FAILED — не удалось',
    )
    failure_reason: str | None = Field(description='Причина неудачной отправки')
    sent_at: datetime | None = Field(description='Момент фактической отправки')
    created_at: datetime = Field(description='Момент постановки в очередь')
    payload: dict = Field(
        description='Данные события: у `automation.change_detected` — `changes` (поле, было, '
        'стало, пробит ли порог) и `changes_text`; у `task.failed` — `error_reason`; у '
        '`task.completed` — `result_count`',
    )


class AdminTaskDetailResponse(TaskDetailResponse):
    """Полная картина задачи: поля задачи, прогресс, аренда воркера и все элементы."""

    claimed_by: str | None = Field(description='Воркер, держащий аренду задачи')
    claimed_at: datetime | None = Field(description='Момент текущего захвата воркером')
    lease_expires_at: datetime | None = Field(
        description='Момент истечения аренды; в прошлом у RUNNING — воркер, вероятно, упал',
    )
    items: list[AdminTaskItemResponse] = Field(description='Все элементы задачи по порядку')
    notifications: list[AdminTaskNotificationResponse] = Field(
        description='Уведомления, порождённые задачей (пусто — не создавались: событие не '
        'сработало, пользователь не включил канал или это старая доставка без `task_id`)',
    )


class AdminFailedItemResponse(BaseModel):
    """Упавший элемент задачи: оригинальная причина ошибки (на задаче только `item_failed`)."""

    id: UUID = Field(description='Идентификатор элемента задачи')
    input_value: str = Field(description='Ссылка или поисковый запрос')
    error_reason: str | None = Field(description='Причина провала элемента')


class AdminTaskListItemResponse(TaskDetailResponse):
    """Строка админского списка: задача + прогресс + упавшие элементы (до 3)."""

    failed_items: list[AdminFailedItemResponse] = Field(
        default_factory=list, description='Элементы в статусе FAILED с причинами ошибок (до 3)',
    )


class AdminTaskListResponse(BaseModel):
    """Ответ `GET /api/admin/tasks/` — постраничный список задач всех пользователей."""

    items: list[AdminTaskListItemResponse] = Field(description='Задачи на текущей странице')
    meta: PaginationMeta = Field(description='Метаданные пагинации')


class TaskStatusCounts(BaseModel):
    """Счётчики задач группы по статусам; `total` — все статусы вместе."""

    total: int = Field(description='Всего задач')
    QUEUED: int = Field(description='В очереди')
    RUNNING: int = Field(description='Выполняются')
    PAUSED: int = Field(description='На паузе')
    SUCCEEDED: int = Field(description='Успешно завершены')
    FAILED: int = Field(description='Завершены с ошибкой')
    EXPIRED: int = Field(description='Просрочены (не взяты в работу до конца TTL очереди)')
    CANCELLED: int = Field(description='Отменены')


class AdminTaskSummaryResponse(BaseModel):
    """Сводка раздела «Задачи»: пользовательские задачи по статусам за период (`created_at`).
    Проверочные задачи автоматизаций считаются в `GET /api/admin/automations/summary`."""

    tasks: TaskStatusCounts = Field(description='Пользовательские задачи')


class RestartTaskRequest(BaseModel):
    """Тело запроса `POST /api/admin/tasks/{task_id}/restart`."""

    ttl_seconds: int = Field(
        description='Через сколько секунд перезапущенная задача считается просроченной, если не '
        'взята в работу (отсчёт от момента перезапуска)',
        gt=0,
    )
