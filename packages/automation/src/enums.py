from enum import Enum


class AutomationStatus(str, Enum):
    ACTIVE = 'ACTIVE'
    PAUSED = 'PAUSED'


class TrackedField(str, Enum):
    """Каждое отслеживаемое поле карточки товара — единый плоский словарь имён полей, заменяет
    прежние раздельные PriceField/StockField: AutomationCheckLog.snapshot/changes и события
    packages/notifications должны ссылаться на поля одинаково, независимо от их типа."""

    PRICE = 'PRICE'
    DISCOUNTED_PRICE = 'DISCOUNTED_PRICE'
    ORIGINAL_PRICE = 'ORIGINAL_PRICE'
    IN_STOCK = 'IN_STOCK'
    TITLE = 'TITLE'
    RATING = 'RATING'
    REVIEW_COUNT = 'REVIEW_COUNT'
    SELLER_NAME = 'SELLER_NAME'


class TrackedFieldKind(str, Enum):
    """Как типизировано и сравнивается значение поля — определяет, участвует ли поле в
    threshold_breached-математике (только KOPECKS + особый случай IN_STOCK) или только в
    generic-сравнении на изменения относительно предыдущего тика."""

    KOPECKS = 'KOPECKS'
    BOOLEAN = 'BOOLEAN'
    NUMERIC = 'NUMERIC'
    TEXT = 'TEXT'
