from datetime import datetime

from pydantic import BaseModel, Field

from apps.api.src.routers.schema import PaginationMeta
from packages.notifications.src.enums import NotificationChannel, NotificationDeliveryStatus

# --- Переиспользуемые сущности ---


class NotificationEventResponse(BaseModel):
    """Одна строка каталога типов событий (GET /api/notifications/events)."""

    event_code: str = Field(description='Код типа события')
    description: str = Field(description='Описание события для UI')
    available_fields: list[str] | None = Field(
        description='Поля, по которым можно фильтровать подписку на это событие; null/пусто — '
        'у события нет понятия "поле"',
    )


class NotificationEventPreferenceItem(BaseModel):
    """Настройка одного события внутри карты preferences — сколько каналов и опциональный фильтр
    по полям (см. NotificationEventResponse.available_fields)."""

    channels: list[NotificationChannel] = Field(
        description='Каналы, на которые слать уведомление по этому событию',
    )
    fields: list[str] | None = Field(
        default=None,
        description='Подмножество available_fields события; null/пусто — уведомлять по любому '
        'изменению, иначе только если затронуто хотя бы одно из перечисленных полей',
    )


class NotificationDeliveryResponse(BaseModel):
    """Одна запись журнала уведомлений, поставленных в очередь
    (GET /api/notifications/deliveries)."""

    id: int = Field(description='Идентификатор строки журнала')
    event_code: str = Field(description='Код события, вызвавшего доставку')
    channel: NotificationChannel = Field(description='Канал доставки')
    status: NotificationDeliveryStatus = Field(description='Статус доставки')
    payload: dict = Field(description='Данные события для отправителя')
    created_at: datetime = Field(description='Момент постановки в очередь')


# --- Запросы ---


class UpdatePreferencesRequest(BaseModel):
    """Тело запроса PUT /api/notifications/preferences — полная замена карты настроек."""

    preferences: dict[str, NotificationEventPreferenceItem] = Field(
        description='Карта {event_code: {channels, fields}}; отсутствие ключа или пустой список '
        'каналов — уведомления по этому событию выключены',
    )


# --- Ответы ---


class NotificationEventListResponse(BaseModel):
    """Ответ GET /api/notifications/events."""

    items: list[NotificationEventResponse] = Field(description='Активные типы событий')


class NotificationPreferencesResponse(BaseModel):
    """Ответ GET/PUT /api/notifications/preferences — текущие настройки пользователя."""

    preferences: dict[str, NotificationEventPreferenceItem] = Field(
        description='Карта {event_code: {channels, fields}}',
    )
    updated_at: datetime = Field(description='Время последнего изменения настроек')


class NotificationDeliveryListResponse(BaseModel):
    """Ответ GET /api/notifications/deliveries."""

    items: list[NotificationDeliveryResponse] = Field(description='Записи журнала на текущей странице')
    meta: PaginationMeta = Field(description='Метаданные пагинации')
