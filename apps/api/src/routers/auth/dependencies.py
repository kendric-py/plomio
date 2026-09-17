from dependency_injector.wiring import Provide, inject
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from apps.api.src.container import DependencyContainer
from core.exceptions import ObjectNotFoundError
from packages.auth.src.exceptions import InvalidTokenError
from packages.auth.src.security import decode_access_token
from packages.user.src.entities import UserEntity
from packages.user.src.service import UserService

bearer_scheme = HTTPBearer()


def get_client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@inject
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    user_service: UserService = Depends(Provide[DependencyContainer.user_service]),
) -> UserEntity:
    try:
        user_id = decode_access_token(token=credentials.credentials)
    except InvalidTokenError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Invalid or expired token',
        ) from error

    try:
        return await user_service.get_by_id(user_id=user_id)
    except ObjectNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='User not found',
        ) from error
