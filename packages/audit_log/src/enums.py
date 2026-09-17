from enum import Enum


class AuditActionType(str, Enum):
    CREATE = 'CREATE'
    UPDATE = 'UPDATE'
    DELETE = 'DELETE'
    AUTH = 'AUTH'


class AuditStatus(str, Enum):
    SUCCESS = 'SUCCESS'
    FAILURE = 'FAILURE'


class AuditAction(str, Enum):
    """Единый реестр всех действий, которые пишутся в audit_logs.

    Сервис, логирующий действие, берёт значение отсюда, а не пишет строку
    'AuthService.register_user' на месте вызова — так все audit-события видны
    в одном файле и не расходятся между собой (опечатки, дубли и т.п.).
    """

    AUTH_REGISTER_USER = 'AuthService.register_user'
    AUTH_AUTHENTICATE_USER = 'AuthService.authenticate_user'
