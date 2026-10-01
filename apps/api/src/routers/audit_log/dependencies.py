from fastapi import Depends, Query

from apps.api.src.routers.dependencies import get_date_range
from apps.api.src.routers.schema import DateRange
from packages.audit_log.src.entities import AuditLogFilters
from packages.audit_log.src.enums import AuditAction, AuditActionType, AuditStatus


def get_audit_log_filters(
    user_id: int | None = Query(default=None, description='Кто выполнил действие'),
    action: AuditAction | None = Query(default=None, description='Действие-источник события'),
    action_type: AuditActionType | None = Query(default=None, description='Тип действия'),
    audit_status: AuditStatus | None = Query(
        default=None, alias='status', description='Результат действия',
    ),
    error_reason: str | None = Query(default=None, description='Код причины неуспеха'),
    target_type: str | None = Query(default=None, description='Тип сущности (например, User)'),
    target_id: int | None = Query(default=None, description='Идентификатор сущности'),
    ip_address: str | None = Query(default=None, description='IP-адрес (точное совпадение)'),
    date_range: DateRange = Depends(get_date_range),
) -> AuditLogFilters:
    """Опциональные фильтры журнала аудита; комбинируются через AND, период — по `created_at`."""
    return AuditLogFilters(
        user_id=user_id,
        action=action,
        action_type=action_type,
        status=audit_status,
        error_reason=error_reason,
        target_type=target_type,
        target_id=target_id,
        ip_address=ip_address,
        date_from=date_range.date_from,
        date_to=date_range.date_to,
    )
