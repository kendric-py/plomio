class AutomationError(Exception):
    """Базовое исключение доменной области automation."""


class InvalidCheckFrequencyError(AutomationError):
    """Частота проверки ниже минимума, заданного в конфиге."""


class DuplicateAutomationError(AutomationError):
    """Пользователь уже отслеживает этот товар в рамках этого маркетплейса — совпадение по
    извлечённому артикулу, а если его не удалось извлечь — по точному совпадению input_value.
    Учитывается автоматизация в любом статусе (ACTIVE и PAUSED), не только активная."""
