from packages.billing.src.exceptions import InsufficientCreditsError


class ApiKeyError(Exception):
    """Базовое исключение доменной области api_keys."""


class InvalidApiKeyError(ApiKeyError):
    """Ключа с таким значением нет."""

    detail = 'Invalid API key'


class ApiKeyRevokedError(ApiKeyError):
    """Ключ отозван: им нельзя авторизоваться и его нельзя изменить."""

    detail = 'API key is revoked'


class ApiKeyExpiredError(ApiKeyError):
    """Срок действия ключа истёк."""

    detail = 'API key is expired'


class InvalidApiKeyExpiryError(ApiKeyError):
    """Срок действия ключа задан в прошлом."""

    detail = 'expires_at must be in the future'


class ApiKeyQuotaExceededError(ApiKeyError):
    """У пользователя уже максимум действующих (не отозванных) ключей."""

    detail = 'Too many API keys'


class ApiKeyCreditLimitExceededError(InsufficientCreditsError):
    """Ключ потратил свой лимит кредитов. Подкласс `InsufficientCreditsError`: блокирует то же,
    что нулевой баланс, поэтому все обработчики 402 ловят его без изменений."""

    detail = 'API key credit limit reached'


class ApiKeyInactiveError(InsufficientCreditsError):
    """Ключ отозван или истёк — траты по нему (возобновление задачи, проверки автоматизаций,
    созданных ключом) запрещены. Тоже 402, как и исчерпанный лимит."""

    detail = 'API key is revoked or expired'
