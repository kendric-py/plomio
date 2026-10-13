from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, status

from apps.api.src.container import DependencyContainer
from apps.api.src.routers.api_keys.dependencies import (
    api_key_not_found,
    audit_details,
    build_api_key_response,
    record_api_key_audit,
    to_api_key_response,
)
from apps.api.src.routers.api_keys.schema import (
    ApiKeyListResponse,
    ApiKeyResponse,
    CreateApiKeyRequest,
    CreateApiKeyResponse,
    UpdateApiKeyRequest,
)
from apps.api.src.routers.auth.dependencies import get_client_ip, get_session_user
from core.exceptions import ObjectNotFoundError
from packages.api_keys.src.entities import ApiKeyUpdateData, ApiKeyWithSpendingEntity
from packages.api_keys.src.exceptions import (
    ApiKeyQuotaExceededError,
    ApiKeyRevokedError,
    InvalidApiKeyExpiryError,
)
from packages.api_keys.src.service import ApiKeyService
from packages.audit_log.src.enums import AuditAction, AuditActionType
from packages.audit_log.src.service import AuditLogService
from packages.user.src.entities import UserEntity

# Управление ключами — только из сессии фронтенда (JWT), не самим API-ключом.
router = APIRouter(prefix='/api-keys', tags=['API Keys'])


@router.get('/')
@inject
async def list_api_keys(
    current_user: UserEntity = Depends(get_session_user),
    api_key_service: ApiKeyService = Depends(Provide[DependencyContainer.api_key_service]),
) -> ApiKeyListResponse:
    api_keys = await api_key_service.list_api_keys(user_id=current_user.id)
    return ApiKeyListResponse(items=[to_api_key_response(api_key=key) for key in api_keys])


@router.post('/', status_code=status.HTTP_201_CREATED)
@inject
async def create_api_key(
    body: CreateApiKeyRequest,
    ip_address: str | None = Depends(get_client_ip),
    current_user: UserEntity = Depends(get_session_user),
    api_key_service: ApiKeyService = Depends(Provide[DependencyContainer.api_key_service]),
    audit_log_service: AuditLogService = Depends(Provide[DependencyContainer.audit_log_service]),
) -> CreateApiKeyResponse:
    try:
        api_key, raw_key = await api_key_service.create_api_key(
            user_id=current_user.id,
            name=body.name,
            credit_limit=body.credit_limit,
            expires_at=body.expires_at,
        )
    except InvalidApiKeyExpiryError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=error.detail,
        ) from error
    except ApiKeyQuotaExceededError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=error.detail) from error

    created = ApiKeyWithSpendingEntity(**api_key.model_dump(), spent_credits=0)
    await record_api_key_audit(
        audit_log_service=audit_log_service,
        action=AuditAction.API_KEY_CREATE,
        action_type=AuditActionType.CREATE,
        api_key_id=created.id,
        user_id=current_user.id,
        ip_address=ip_address,
        details=audit_details(api_key=created),
    )
    return CreateApiKeyResponse.model_validate(
        obj={**build_api_key_response(api_key=created), 'key': raw_key},
    )


@router.get('/{api_key_id}')
@inject
async def get_api_key(
    api_key_id: int,
    current_user: UserEntity = Depends(get_session_user),
    api_key_service: ApiKeyService = Depends(Provide[DependencyContainer.api_key_service]),
) -> ApiKeyResponse:
    try:
        api_key = await api_key_service.get_api_key(api_key_id=api_key_id, user_id=current_user.id)
    except ObjectNotFoundError as error:
        raise api_key_not_found() from error
    return to_api_key_response(api_key=api_key)


@router.patch('/{api_key_id}')
@inject
async def update_api_key(
    api_key_id: int,
    body: UpdateApiKeyRequest,
    ip_address: str | None = Depends(get_client_ip),
    current_user: UserEntity = Depends(get_session_user),
    api_key_service: ApiKeyService = Depends(Provide[DependencyContainer.api_key_service]),
    audit_log_service: AuditLogService = Depends(Provide[DependencyContainer.audit_log_service]),
) -> ApiKeyResponse:
    changes = ApiKeyUpdateData.model_validate(
        obj=body.model_dump(include=body.model_fields_set),
    )
    try:
        api_key = await api_key_service.update_api_key(
            api_key_id=api_key_id, user_id=current_user.id, changes=changes,
        )
    except ObjectNotFoundError as error:
        raise api_key_not_found() from error
    except ApiKeyRevokedError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=error.detail) from error
    except InvalidApiKeyExpiryError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=error.detail,
        ) from error

    await record_api_key_audit(
        audit_log_service=audit_log_service,
        action=AuditAction.API_KEY_UPDATE,
        action_type=AuditActionType.UPDATE,
        api_key_id=api_key_id,
        user_id=current_user.id,
        ip_address=ip_address,
        details={**audit_details(api_key=api_key), 'changed': sorted(body.model_fields_set)},
    )
    return to_api_key_response(api_key=api_key)


@router.post('/{api_key_id}/revoke')
@inject
async def revoke_api_key(
    api_key_id: int,
    ip_address: str | None = Depends(get_client_ip),
    current_user: UserEntity = Depends(get_session_user),
    api_key_service: ApiKeyService = Depends(Provide[DependencyContainer.api_key_service]),
    audit_log_service: AuditLogService = Depends(Provide[DependencyContainer.audit_log_service]),
) -> ApiKeyResponse:
    try:
        api_key = await api_key_service.revoke_api_key(
            api_key_id=api_key_id, user_id=current_user.id,
        )
    except ObjectNotFoundError as error:
        raise api_key_not_found() from error

    await record_api_key_audit(
        audit_log_service=audit_log_service,
        action=AuditAction.API_KEY_REVOKE,
        action_type=AuditActionType.DELETE,
        api_key_id=api_key_id,
        user_id=current_user.id,
        ip_address=ip_address,
        details=audit_details(api_key=api_key),
    )
    return to_api_key_response(api_key=api_key)
