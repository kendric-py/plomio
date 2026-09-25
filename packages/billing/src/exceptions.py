class BillingError(Exception):
    """Базовое исключение доменной области billing."""


class InsufficientCreditsError(BillingError):
    """Баланс пользователя <= 0 — блокирует создание новых задач/автоматизаций и диспатч уже
    существующих активных автоматизаций, пока баланс не пополнит админ."""


class OverlappingPricingRuleError(BillingError):
    """Новый диапазон `pricing_multiplier_rules` пересекается с уже существующим правилом в рамках
    того же `dimension_code`."""
