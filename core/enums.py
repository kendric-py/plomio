from enum import Enum


class Marketplace(str, Enum):
    OZON = 'ozon'
    WILDBERRIES = 'wildberries'


class BucketUnit(str, Enum):
    """Шаг группировки временного ряда (`date_trunc`) для агрегатов по времени."""

    MINUTE = 'minute'
    HOUR = 'hour'
    DAY = 'day'
