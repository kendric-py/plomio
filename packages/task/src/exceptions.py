class TaskError(Exception):
    """Базовое исключение доменной области task."""


class InvalidTaskTransitionError(TaskError):
    """Недопустимый переход статуса задачи (например, отмена уже завершённой задачи)."""


class TaskItemNotExcludableError(TaskError):
    """Из задачи можно исключить только элемент в статусе FAILED."""
