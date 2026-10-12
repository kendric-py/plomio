# Коды событий, которые домены кладут в `NotificationService.notify`/`notify_admins`, и их аудитория.
EVENT_SESSIONS_DEPLETED = 'system.sessions_depleted'
EVENT_SESSIONS_RESTORED = 'system.sessions_restored'

# События только для администраторов: клиент не видит их в `GET /events` и не может включить их
# в своих настройках (`update_preferences` отвечает как на неизвестное событие).
ADMIN_ONLY_EVENT_CODES = frozenset({EVENT_SESSIONS_DEPLETED, EVENT_SESSIONS_RESTORED})
