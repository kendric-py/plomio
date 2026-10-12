from enum import Enum


class OverviewWindow(str, Enum):
    """Окно сводки `GET /api/admin/overview`: за какой период считаются счётчики и графики."""

    HOUR = '1h'
    DAY = '24h'
    WEEK = '7d'
