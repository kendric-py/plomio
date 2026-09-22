from enum import Enum


class CronJobName(str, Enum):
    """Единый реестр периодических job'ов, запускаемых `packages.cron.src.scheduler.run_periodic`.

    Новый job сначала регистрируется здесь, потом используется при вызове `run_periodic` —
    как `AuditAction` в `packages/audit_log`."""

    WORKER_HEARTBEAT_SWEEP = 'WORKER_HEARTBEAT_SWEEP'
    TASK_EXPIRY_SWEEP = 'TASK_EXPIRY_SWEEP'
    AUTOMATION_DISPATCH = 'AUTOMATION_DISPATCH'
    AUTOMATION_RESULT_SWEEP = 'AUTOMATION_RESULT_SWEEP'
    AUTOMATION_HISTORY_RETENTION_SWEEP = 'AUTOMATION_HISTORY_RETENTION_SWEEP'


class CronJobStatus(str, Enum):
    SUCCESS = 'SUCCESS'
    FAILURE = 'FAILURE'
