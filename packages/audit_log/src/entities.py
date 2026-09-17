from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from packages.audit_log.src.enums import AuditAction, AuditActionType, AuditStatus


class AuditLogEntity(BaseModel):
    id: Optional[int] = Field(default=None, description='Идентификатор записи')
    action: Optional[AuditAction] = Field(default=None, description='Действие-источник события')
    action_type: Optional[AuditActionType] = Field(default=None, description='Тип действия')
    status: Optional[AuditStatus] = Field(default=None, description='Результат действия')
    details: Optional[dict] = Field(default=None, description='Стандартизированные детали действия')
    error_reason: Optional[str] = Field(default=None, description='Код причины неуспеха')
    target_type: Optional[str] = Field(
        default=None,
        description='Тип сущности, над которой произведено действие',
    )
    target_id: Optional[int] = Field(
        default=None,
        description='Идентификатор сущности, над которой произведено действие',
    )
    user_id: Optional[int] = Field(
        default=None,
        description='Идентификатор пользователя, выполнившего действие',
    )
    ip_address: Optional[str] = Field(
        default=None,
        description='IP-адрес, с которого выполнено действие',
    )
    created_at: Optional[datetime] = Field(default=None, description='Время создания записи')
