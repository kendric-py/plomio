from datetime import datetime

from pydantic import BaseModel, Field

from apps.api.src.routers.schema import PaginationMeta
from packages.audit_log.src.enums import AuditAction, AuditActionType, AuditStatus


class AuditLogResponse(BaseModel):
    id: int = Field(description='Идентификатор записи')
    action: AuditAction = Field(description='Действие-источник события')
    action_type: AuditActionType = Field(description='Тип действия')
    status: AuditStatus = Field(description='Результат действия')
    details: dict = Field(description='Детали: {"fields": {поле: {"before": ..., "after": ...}}}')
    error_reason: str | None = Field(description='Код причины неуспеха; null при успехе')
    target_type: str | None = Field(description='Тип сущности, над которой выполнено действие')
    target_id: int | None = Field(description='Идентификатор этой сущности')
    user_id: int | None = Field(description='Кто выполнил действие; null — актор не определён')
    ip_address: str | None = Field(description='IP-адрес, с которого выполнено действие')
    created_at: datetime = Field(description='Время создания записи')


class AuditLogListResponse(BaseModel):
    """Ответ `GET /api/admin/audit-logs/` — постраничный журнал аудита."""

    items: list[AuditLogResponse] = Field(description='Записи на текущей странице')
    meta: PaginationMeta
