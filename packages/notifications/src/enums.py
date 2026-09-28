from enum import Enum


class NotificationChannel(str, Enum):
    """Провайдер-агностичный канал доставки. Сейчас единственное значение — новый провайдер
    добавляется новым значением enum + реализацией отправителя (не входит в эту итерацию, см.
    AGENTS.md), схема БД не меняется."""

    TELEGRAM = 'TELEGRAM'


class NotificationDeliveryStatus(str, Enum):
    """Жизненный цикл поставленного в очередь уведомления. `notify()` создаёт только PENDING;
    `NotificationService.dispatch_pending` переводит строки в SENT/FAILED."""

    PENDING = 'PENDING'
    SENT = 'SENT'
    FAILED = 'FAILED'


class TelegramLinkOutcome(str, Enum):
    """Результат `NotificationService.confirm_telegram_link` — определяет, каким текстом бот
    отвечает пользователю в Telegram (см. `packages.notifications.src.telegram_polling`)."""

    LINKED = 'LINKED'
    ALREADY_LINKED_SAME = 'ALREADY_LINKED_SAME'
    ALREADY_LINKED_OTHER = 'ALREADY_LINKED_OTHER'
    INVALID_CODE = 'INVALID_CODE'
