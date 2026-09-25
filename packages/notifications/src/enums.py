from enum import Enum


class NotificationChannel(str, Enum):
    """Провайдер-агностичный канал доставки. Сейчас единственное значение — новый провайдер
    добавляется новым значением enum + реализацией отправителя (не входит в эту итерацию, см.
    AGENTS.md), схема БД не меняется."""

    TELEGRAM = 'TELEGRAM'


class NotificationDeliveryStatus(str, Enum):
    """Жизненный цикл поставленного в очередь уведомления. В этой итерации создаются только
    PENDING — реальный отправитель (будущая работа) будет переводить строки в SENT/FAILED."""

    PENDING = 'PENDING'
    SENT = 'SENT'
    FAILED = 'FAILED'
