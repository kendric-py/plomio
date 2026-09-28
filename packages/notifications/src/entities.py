from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from packages.notifications.src.enums import NotificationChannel, NotificationDeliveryStatus


class NotificationTemplateVariableEntity(BaseModel):
    """Значение одной записи `packages.notifications.src.template_catalog.TEMPLATE_VARIABLES` —
    не сущность БД (это код-владеемый каталог, не таблица), доменный value object, переиспользуемый
    и сервисом, и REST-схемой."""

    field: Optional[str] = Field(
        default=None,
        description='Имя поля, на которое подписывает использование этой переменной в шаблоне '
        '(см. NotificationService.notify, "Фильтрация по переменным шаблона"); null — переменная '
        'контекстная, ни на что не подписывает',
    )
    description: str = Field(
        default='',
        description='Человекочитаемое описание переменной для UI — что именно она подставляет '
        '(например, "Цена со скидкой на предыдущей проверке")',
    )
    is_money: bool = Field(
        default=False,
        description='Значение переменной — сумма в копейках; при рендере в шаблон подставляется '
        'как рубли (например, 150000 -> "1 500,00 ₽"), а не сырое число копеек',
    )


class NotificationEventEntity(BaseModel):
    event_code: Optional[str] = Field(default=None, description='Код типа события (PK)')
    description: Optional[str] = Field(default=None, description='Описание события для UI')
    is_active: Optional[bool] = Field(
        default=None,
        description='Активно ли событие; неактивное событие никогда не создаёт доставок',
    )
    available_fields: Optional[list[str]] = Field(
        default=None,
        description='Имена полей, по которым можно фильтровать подписку на это событие; '
        'null/пусто — у события нет понятия "поле", фильтр неприменим',
    )


class NotificationEventPreference(BaseModel):
    """Значение одной записи карты NotificationSetting.preferences — не самостоятельная сущность
    БД, доменный value object, переиспользуемый и сервисом, и REST-схемой."""

    channels: list[NotificationChannel] = Field(
        default_factory=list, description='Каналы, на которые слать уведомление по этому событию',
    )
    fields: Optional[list[str]] = Field(
        default=None,
        description='Подмножество available_fields события; null/пусто — уведомлять по любому '
        'изменению, иначе только если затронуто хотя бы одно из перечисленных полей',
    )
    template: Optional[str] = Field(
        default=None,
        description='Пользовательский шаблон текста сообщения ({переменные} из ключей '
        'NotificationEvent.template_variables); null — использовать встроенный текст по '
        'умолчанию (packages.notifications.src.formatting)',
    )


class NotificationSettingEntity(BaseModel):
    user_id: Optional[int] = Field(default=None, description='Идентификатор пользователя')
    preferences: Optional[dict[str, NotificationEventPreference]] = Field(
        default=None,
        description='Карта {event_code: {channels, fields}}; отсутствие ключа или пустой список '
        'каналов — уведомления по этому событию выключены',
    )
    created_at: Optional[datetime] = Field(default=None, description='Время создания настроек')
    updated_at: Optional[datetime] = Field(
        default=None,
        description='Время последнего изменения настроек',
    )


class NotificationDeliveryEntity(BaseModel):
    id: Optional[int] = Field(default=None, description='Идентификатор строки журнала')
    user_id: Optional[int] = Field(default=None, description='Идентификатор пользователя')
    event_code: Optional[str] = Field(default=None, description='Код события, вызвавшего доставку')
    channel: Optional[NotificationChannel] = Field(default=None, description='Канал доставки')
    status: Optional[NotificationDeliveryStatus] = Field(
        default=None,
        description='Статус доставки; в этой итерации создаются только PENDING',
    )
    payload: Optional[dict] = Field(
        default=None,
        description='Произвольные данные события для будущего отправителя',
    )
    failure_reason: Optional[str] = Field(
        default=None,
        description='Причина неудачи отправки; заполняется будущим отправителем',
    )
    sent_at: Optional[datetime] = Field(
        default=None,
        description='Момент фактической отправки; заполняется будущим отправителем',
    )
    created_at: Optional[datetime] = Field(default=None, description='Момент постановки в очередь')
