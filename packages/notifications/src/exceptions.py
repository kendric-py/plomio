class NotificationError(Exception):
    """Базовое исключение доменной области notifications."""


class UnknownNotificationEventError(NotificationError):
    """event_code отсутствует в каталоге notification_events или помечен неактивным
    (is_active=False) — попытка включить его в preferences пользователя."""


class InvalidNotificationFieldFilterError(NotificationError):
    """preferences[event_code].fields содержит значение, не входящее в available_fields этого
    события (либо у события вообще нет available_fields, а fields всё равно передан)."""
