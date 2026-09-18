from enum import Enum

from pydantic import BaseModel, Field

from apps.worker_parser.src.exceptions import (
    BlockedError,
    BrowserInitError,
    InputResolutionError,
    ParserError,
    RequestError,
    SuspiciousThinResultError,
    UpstreamDataError,
)
from packages.task.src.enums import TaskItemStatus


class SessionAction(str, Enum):
    KEEP = 'KEEP'
    REINIT_SESSION = 'REINIT_SESSION'


class RetryPolicy(BaseModel):
    max_attempts: int = Field(...)
    session_action: SessionAction = Field(...)
    resulting_item_status_on_exhaustion: TaskItemStatus = Field(...)


_DEFAULT_POLICY = RetryPolicy(
    max_attempts=0,
    session_action=SessionAction.KEEP,
    resulting_item_status_on_exhaustion=TaskItemStatus.FAILED,
)

_RETRY_POLICY_MAP: list[tuple[type[ParserError], RetryPolicy]] = [
    (
        SuspiciousThinResultError,
        RetryPolicy(
            max_attempts=3,
            session_action=SessionAction.REINIT_SESSION,
            resulting_item_status_on_exhaustion=TaskItemStatus.FAILED,
        ),
    ),
    (
        BlockedError,
        RetryPolicy(
            max_attempts=3,
            session_action=SessionAction.REINIT_SESSION,
            resulting_item_status_on_exhaustion=TaskItemStatus.FAILED,
        ),
    ),
    (
        RequestError,
        RetryPolicy(
            max_attempts=3,
            session_action=SessionAction.REINIT_SESSION,
            resulting_item_status_on_exhaustion=TaskItemStatus.FAILED,
        ),
    ),
    (
        UpstreamDataError,
        RetryPolicy(
            max_attempts=1,
            session_action=SessionAction.KEEP,
            resulting_item_status_on_exhaustion=TaskItemStatus.FAILED,
        ),
    ),
    (
        InputResolutionError,
        RetryPolicy(
            max_attempts=0,
            session_action=SessionAction.KEEP,
            resulting_item_status_on_exhaustion=TaskItemStatus.FAILED,
        ),
    ),
    (
        BrowserInitError,
        RetryPolicy(
            max_attempts=0,
            session_action=SessionAction.KEEP,
            resulting_item_status_on_exhaustion=TaskItemStatus.FAILED,
        ),
    ),
]


def resolve_retry_policy(error: ParserError) -> RetryPolicy:
    for error_type, policy in _RETRY_POLICY_MAP:
        if isinstance(error, error_type):
            return policy
    return _DEFAULT_POLICY
