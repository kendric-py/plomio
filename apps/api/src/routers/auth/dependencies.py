from dependency_injector.wiring import Provide, inject
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

from apps.api.src.container import DependencyContainer
from core.exceptions import ObjectNotFoundError
from packages.api_keys.src.entities import ApiKeyEntity
from packages.api_keys.src.exceptions import (
    ApiKeyExpiredError,
    ApiKeyRevokedError,
    InvalidApiKeyError,
)
from packages.api_keys.src.security import looks_like_api_key
from packages.api_keys.src.service import ApiKeyService
from packages.auth.src.exceptions import InvalidTokenError
from packages.auth.src.security import decode_access_token
from packages.user.src.entities import UserEntity
from packages.user.src.service import UserService

API_KEY_HEADER = 'X-API-Key'

# auto_error=False: оба способа необязательны по отдельности, отсутствие обоих — 401 ниже.
bearer_scheme = HTTPBearer(
    auto_error=False,
    description='JWT из POST /api/auth/login, либо API-ключ (plm_...)',
)
api_key_scheme = APIKeyHeader(
    name=API_KEY_HEADER,
    auto_error=False,
    description='API-ключ из раздела «API-ключи» (plm_...)',
)


class AuthContext(BaseModel):
    """Кто выполняет запрос: пользователь и API-ключ, если запрос пришёл с ключом (а не с JWT
    фронтенда). Зависимость кэшируется FastAPI в рамках запроса — ключ проверяется один раз."""

    model_config = ConfigDict(frozen=True)

    user: UserEntity = Field(description='Владелец JWT или API-ключа')
    api_key: ApiKeyEntity | None = Field(default=None, description='Ключ запроса; None — JWT')


def get_client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={'WWW-Authenticate': 'Bearer'},
    )


@inject
async def get_auth_context(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    header_api_key: str | None = Depends(api_key_scheme),
    user_service: UserService = Depends(Provide[DependencyContainer.user_service]),
    api_key_service: ApiKeyService = Depends(Provide[DependencyContainer.api_key_service]),
) -> AuthContext:
    """API-ключ — в `X-API-Key` или в `Authorization: Bearer plm_...` (отличается от JWT
    префиксом); иначе `Authorization: Bearer <JWT>`."""
    bearer_value = credentials.credentials if credentials is not None else None
    raw_api_key = header_api_key or (
        bearer_value if bearer_value and looks_like_api_key(value=bearer_value) else None
    )

    api_key = None
    if raw_api_key is not None:
        try:
            api_key = await api_key_service.authenticate(raw_key=raw_api_key)
        except (InvalidApiKeyError, ApiKeyRevokedError, ApiKeyExpiredError) as error:
            raise _unauthorized(detail=error.detail) from error
        user_id = api_key.user_id
    elif bearer_value is not None:
        try:
            user_id = decode_access_token(token=bearer_value)
        except InvalidTokenError as error:
            raise _unauthorized(detail='Invalid or expired token') from error
    else:
        raise _unauthorized(detail='Not authenticated')

    try:
        user = await user_service.get_by_id(user_id=user_id)
    except ObjectNotFoundError as error:
        raise _unauthorized(detail='User not found') from error
    return AuthContext(user=user, api_key=api_key)


async def get_current_user(context: AuthContext = Depends(get_auth_context)) -> UserEntity:
    return context.user


async def get_current_api_key_id(context: AuthContext = Depends(get_auth_context)) -> int | None:
    """Ключ запроса для учёта трат (`api_key_id` у задач, автоматизаций и списаний)."""
    return context.api_key.id if context.api_key is not None else None


async def get_session_user(context: AuthContext = Depends(get_auth_context)) -> UserEntity:
    """Только JWT (сессия фронтенда): управление ключами и админка через API-ключ недоступны —
    утёкший ключ не должен уметь выпускать новые ключи, снимать себе лимит или действовать от
    имени администратора."""
    if context.api_key is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Not available with an API key',
        )
    return context.user
