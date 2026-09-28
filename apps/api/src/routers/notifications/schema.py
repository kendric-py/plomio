from datetime import datetime

from pydantic import BaseModel, Field

from apps.api.src.routers.schema import PaginationMeta
from packages.notifications.src.enums import NotificationChannel, NotificationDeliveryStatus

# --- Переиспользуемые сущности ---


class TemplateVariableResponse(BaseModel):
    """Одна переменная, допустимая в пользовательском шаблоне события — часть карты
    NotificationEventResponse.template_variables."""

    field: str | None = Field(
        description='Имя поля, на изменения которого подписывает использование этой переменной '
        'в шаблоне; null — переменная контекстная, ни на что не подписывает (см. "fields" в '
        'NotificationEventPreferenceItem и template там же)',
    )
    description: str = Field(
        description='Человекочитаемое описание переменной для UI — что именно она подставляет',
    )
    is_money: bool = Field(
        description='true — в payload это копейки, но в отправленном сообщении переменная '
        'подставится как рубли (например, "1 500,00 ₽")',
    )


class NotificationEventResponse(BaseModel):
    """Одна строка каталога типов событий (GET /api/notifications/events)."""

    event_code: str = Field(description='Код типа события')
    description: str = Field(description='Описание события для UI')
    available_fields: list[str] | None = Field(
        description='Поля, по которым можно фильтровать подписку на это событие; null/пусто — '
        'у события нет понятия "поле"',
    )
    template_variables: dict[str, TemplateVariableResponse] | None = Field(
        description='Карта {переменная: {field, description}} — какие {name} можно использовать '
        'в пользовательском шаблоне этого события (см. NotificationEventPreferenceItem.template)',
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
        'изменению, иначе только если затронуто хотя бы одно из перечисленных полей. '
        'Игнорируется, если задан template — тогда фильтр выводится из полей, на которые '
        'ссылаются переменные шаблона (см. template)',
    )
    template: str | None = Field(
        default=None,
        description='Пользовательский текст сообщения ({переменные} — ключи '
        'NotificationEventResponse.template_variables этого события, например "{product_name}"); '
        'null — использовать встроенный текст по умолчанию. Если задан — постановка в очередь '
        'фильтруется по полям, которые шаблон реально использует (template_variables[var] '
        'непустой для использованных var), а не по отдельному fields',
    )


class NotificationDeliveryResponse(BaseModel):
    """Одна запись журнала уведомлений, поставленных в очередь
    (GET /api/notifications/deliveries)."""

    id: int = Field(description='Идентификатор строки журнала')
    event_code: str = Field(description='Код события, вызвавшего доставку')
    channel: NotificationChannel = Field(description='Канал доставки')
    status: NotificationDeliveryStatus = Field(description='Статус доставки')
    payload: dict = Field(description='Данные события для отправителя')
    failure_reason: str | None = Field(
        default=None, description='Причина неудачи отправки (только при status=FAILED)',
    )
    sent_at: datetime | None = Field(
        default=None, description='Момент фактической отправки (только при status=SENT)',
    )
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


class CreateTelegramLinkResponse(BaseModel):
    """Ответ POST /api/notifications/telegram/link — одноразовая ссылка для привязки Telegram
    (см. packages/notifications/AGENTS.md, "Привязка Telegram")."""

    deep_link: str = Field(description='Ссылка t.me/<bot>?start=<code> для перехода в Telegram')
    expires_in_seconds: int = Field(description='Через сколько секунд код станет недействителен')
