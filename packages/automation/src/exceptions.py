class AutomationError(Exception):
    """Базовое исключение доменной области automation."""


class InvalidCheckFrequencyError(AutomationError):
    """Частота проверки ниже минимума, заданного в конфиге."""
