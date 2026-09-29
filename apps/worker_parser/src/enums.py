from enum import Enum


class WorkerParserStatus(str, Enum):
    """Reported in the process-level liveness heartbeat (`LivenessReporter`,
    packages/worker_health). Minimum set required by the project brief: ready to claim work,
    actively working a claimed task, and blocked waiting on a Redis session from worker_sessions.
    Extend if a real deployment surfaces a state that doesn't fit any of these (e.g. a
    graceful-shutdown state)."""

    READY = 'READY'
    WORKING = 'WORKING'
    WAITING_FOR_SESSION = 'WAITING_FOR_SESSION'


class ErrorOutcome(str, Enum):
    """Исход ошибки парсера для потребителя, которому нужен статус, а не политика ретраев
    (direct-режим). Режим задач этот классификатор не использует — ему достаточно `RetryPolicy`."""

    INVALID_INPUT = 'INVALID_INPUT'
    NOT_FOUND = 'NOT_FOUND'
    UNAVAILABLE = 'UNAVAILABLE'
    ERROR = 'ERROR'


class WorkerMode(str, Enum):
    """Один процесс — один режим: задачи из очереди Postgres или синхронные direct-запросы из
    Redis. Смешивать нельзя: у режимов разные зависимости (direct не нужен Postgres) и разная
    модель нагрузки."""

    TASKS = 'tasks'
    DIRECT = 'direct'
