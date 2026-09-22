from enum import Enum


class AutomationStatus(str, Enum):
    ACTIVE = 'ACTIVE'
    PAUSED = 'PAUSED'


class PriceField(str, Enum):
    PRICE = 'PRICE'
    DISCOUNTED_PRICE = 'DISCOUNTED_PRICE'
    ORIGINAL_PRICE = 'ORIGINAL_PRICE'


class StockField(str, Enum):
    """Separate from `PriceField` — `in_stock` is a bool, not a kopecks amount, so it doesn't share
    the price fields' threshold-percent semantics (see `AutomationService._diff_stock`)."""

    IN_STOCK = 'IN_STOCK'
