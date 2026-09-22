from enum import Enum


class AutomationStatus(str, Enum):
    ACTIVE = 'ACTIVE'
    PAUSED = 'PAUSED'


class PriceField(str, Enum):
    PRICE = 'PRICE'
    DISCOUNTED_PRICE = 'DISCOUNTED_PRICE'
    ORIGINAL_PRICE = 'ORIGINAL_PRICE'
