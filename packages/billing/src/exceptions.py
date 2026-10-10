class BillingError(Exception):
    """Базовое исключение доменной области billing."""


class InsufficientCreditsError(BillingError):
    """Баланс пользователя <= 0 — блокирует создание новых задач/автоматизаций и диспатч уже
    существующих активных автоматизаций, пока баланс не пополнит админ."""

    # Текст для `detail` HTTP 402 — один на все роутеры, чтобы не расходился.
    detail = 'Insufficient credits'


class SpendingLimitExceededError(InsufficientCreditsError):
    """Достигнут лимит расходов, который пользователь задал себе сам (за сутки или за месяц).
    Подкласс `InsufficientCreditsError`: блокирует ровно то же, что и нулевой баланс, поэтому все
    существующие обработчики 402 ловят его без изменений; отличается только текстом."""

    detail = 'Spending limit reached'


class OverlappingPricingRuleError(BillingError):
    """Новый диапазон `pricing_multiplier_rules` пересекается с уже существующим правилом в рамках
    того же `dimension_code`."""
