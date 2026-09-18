from enum import Enum


class CronJobName(str, Enum):
    """Единый реестр периодических job'ов, запускаемых `packages.cron.src.scheduler.run_periodic`.

    Новый job сначала регистрируется здесь, потом используется при вызове `run_periodic` —
    как `AuditAction` в `packages/audit_log`."""

    WORKER_HEARTBEAT_SWEEP = 'WORKER_HEARTBEAT_SWEEP'


class CronJobStatus(str, Enum):
    SUCCESS = 'SUCCESS'
    FAILURE = 'FAILURE'
