from enum import Enum


class ApiKeyStatus(str, Enum):
    """Вычисляемый статус ключа (в БД не хранится): `REVOKED` важнее `EXPIRED`."""

    ACTIVE = 'ACTIVE'
    EXPIRED = 'EXPIRED'
    REVOKED = 'REVOKED'


class ApiKeyBlockReason(str, Enum):
    """Почему по ключу нельзя тратить кредиты. Значение пишется в
    `Automation.last_check_error`, когда проверка пропущена из-за ключа."""

    INACTIVE = 'api_key_inactive'
    CREDIT_LIMIT = 'api_key_credit_limit'
