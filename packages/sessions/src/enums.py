from enum import Enum


class SessionGenerationOutcome(str, Enum):
    """Итог одной попытки генерации сессии: успех либо тип ошибки. Значения ошибок совпадают с
    `errors.py::SessionErrorKind`; в Redis-окне последних генераций хранятся эти строки."""

    SUCCESS = 'success'
    ANTIBOT_INIT = 'antibot_init'
    VALIDATION = 'validation'
    PROXY_UNAVAILABLE = 'proxy_unavailable'
    OTHER = 'other'
