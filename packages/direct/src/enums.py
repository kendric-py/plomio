from enum import Enum


class DirectRequestType(str, Enum):
    PRODUCT_PAGE = 'product_page'
    REVIEWS = 'reviews'
    SEARCH = 'search'
    CATEGORY = 'category'
    SELLER = 'seller'


class DirectStatus(str, Enum):
    """Статус ответа direct-запроса. Причины сбоя (`unavailable`/`error`) в API сводятся к одному
    сообщению клиенту, но в протоколе остаются различимыми — для логов и метрик."""

    OK = 'ok'
    INVALID_INPUT = 'invalid_input'
    NOT_FOUND = 'not_found'
    UNAVAILABLE = 'unavailable'
    ERROR = 'error'


class DirectOutcome(str, Enum):
    """Итог direct-запроса для истории (`direct_requests`): статусы ответа воркера плюс исходы,
    которых воркер не видит — таймаут ожидания ответа и сбой списания кредитов."""

    OK = 'OK'
    INVALID_INPUT = 'INVALID_INPUT'
    NOT_FOUND = 'NOT_FOUND'
    UNAVAILABLE = 'UNAVAILABLE'
    ERROR = 'ERROR'
    TIMEOUT = 'TIMEOUT'
    BILLING_FAILED = 'BILLING_FAILED'
