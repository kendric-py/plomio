import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status

from apps.api.src.routers.api_keys.schema import ApiKeyResponse
from packages.api_keys.src.entities import ApiKeyWithSpendingEntity
from packages.api_keys.src.service import resolve_api_key_status
from packages.audit_log.src.entities import AuditLogEntity
from packages.audit_log.src.enums import AuditAction, AuditActionType, AuditStatus
from packages.audit_log.src.service import AuditLogService

logger = logging.getLogger(__name__)

AUDIT_TARGET_TYPE = 'ApiKey'


def build_api_key_response(api_key: ApiKeyWithSpendingEntity) -> dict:
    """Поля `ApiKeyResponse` из сущности: статус и остаток лимита вычисляются здесь, в БД их нет."""
    remaining = (
        max(api_key.credit_limit - api_key.spent_credits, 0)
        if api_key.credit_limit is not None else None
    )
    return {
        **api_key.model_dump(),
        'status': resolve_api_key_status(api_key=api_key, now=datetime.now(tz=timezone.utc)),
        'remaining_credits': remaining,
    }


def to_api_key_response(api_key: ApiKeyWithSpendingEntity) -> ApiKeyResponse:
    return ApiKeyResponse.model_validate(obj=build_api_key_response(api_key=api_key))


def api_key_not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='API key not found')


async def record_api_key_audit(
    audit_log_service: AuditLogService,
    action: AuditAction,
    action_type: AuditActionType,
    api_key_id: int,
    user_id: int,
    ip_address: str | None,
    details: dict,
) -> None:
    """Действие уже закоммичено — сбой аудита его не откатывает, только логируется. Значение
    ключа в детали не попадает никогда."""
    try:
        await audit_log_service.record(
            entity=AuditLogEntity(
                action=action,
                action_type=action_type,
                status=AuditStatus.SUCCESS,
                details=details,
                target_type=AUDIT_TARGET_TYPE,
                target_id=api_key_id,
                user_id=user_id,
                ip_address=ip_address,
            ),
        )
    except Exception:
        logger.exception('Failed to record audit event %s for api key %s', action, api_key_id)


def audit_details(api_key: ApiKeyWithSpendingEntity) -> dict:
    return {
        'name': api_key.name,
        'prefix': api_key.prefix,
        'credit_limit': api_key.credit_limit,
        'expires_at': api_key.expires_at.isoformat() if api_key.expires_at else None,
    }
