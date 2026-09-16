class DuplicatedObjectError(Exception):
    """Объект нарушает уникальное ограничение БД (например, поле уже занято)."""


class ObjectNotFoundError(Exception):
    """Объект не найден в БД."""
