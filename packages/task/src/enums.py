from enum import Enum


class ParseType(str, Enum):
    PRODUCT_PAGE = 'PRODUCT_PAGE'
    SEARCH_QUERY = 'SEARCH_QUERY'
    REVIEWS = 'REVIEWS'
    CATEGORY = 'CATEGORY'
    SELLER = 'SELLER'


class TaskStatus(str, Enum):
    QUEUED = 'QUEUED'
    RUNNING = 'RUNNING'
    PAUSED = 'PAUSED'
    SUCCEEDED = 'SUCCEEDED'
    FAILED = 'FAILED'
    EXPIRED = 'EXPIRED'
    CANCELLED = 'CANCELLED'


class TaskItemStatus(str, Enum):
    PENDING = 'PENDING'
    RUNNING = 'RUNNING'
    SUCCEEDED = 'SUCCEEDED'
    FAILED = 'FAILED'
    EXCLUDED = 'EXCLUDED'
