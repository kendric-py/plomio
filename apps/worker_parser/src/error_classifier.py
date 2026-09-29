from http import HTTPStatus

from pydantic import BaseModel, Field

from apps.worker_parser.src.enums import ErrorOutcome
from apps.worker_parser.src.exceptions import (
    BrowserInitError,
    DeadlineExceededError,
    InputResolutionError,
    ParserError,
    RequestError,
)
from apps.worker_parser.src.retry_policy import RetryPolicy, resolve_retry_policy


class ErrorClassification(BaseModel):
    """Одна классификация на оба потребителя: политика ретраев нужна циклу выполнения, исход —
    формированию ответа direct. Держать их в одном месте важно, чтобы «что ретраить» и «что
    сказать клиенту» не разъезжались при добавлении нового типа ошибки."""

    policy: RetryPolicy = Field(...)
    outcome: ErrorOutcome = Field(...)


def resolve_error_outcome(error: ParserError) -> ErrorOutcome:
    if isinstance(error, InputResolutionError):
        return ErrorOutcome.INVALID_INPUT
    if isinstance(error, RequestError) and error.status_code == HTTPStatus.NOT_FOUND:
        return ErrorOutcome.NOT_FOUND
    if isinstance(error, (DeadlineExceededError, BrowserInitError)):
        return ErrorOutcome.UNAVAILABLE
    return ErrorOutcome.ERROR


def classify_error(error: ParserError) -> ErrorClassification:
    return ErrorClassification(
        policy=resolve_retry_policy(error), outcome=resolve_error_outcome(error),
    )
