from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, status

from apps.api.src.container import DependencyContainer
from apps.api.src.routers.auth.dependencies import get_client_ip
from apps.api.src.routers.auth.schema import LoginRequest, RegisterRequest, StatusResponse, TokenResponse
from packages.auth.src.exceptions import InvalidCredentialsError, UserAlreadyExistsError
from packages.auth.src.security import create_access_token
from packages.auth.src.service import AuthService

router = APIRouter(prefix='/auth', tags=['Auth'])


@router.get('/status')
@inject
async def get_status(
    auth_service: AuthService = Depends(Provide[DependencyContainer.auth_service]),
) -> StatusResponse:
    return StatusResponse(has_users=await auth_service.has_users())


@router.post('/register', status_code=status.HTTP_201_CREATED)
@inject
async def register(
    body: RegisterRequest,
    ip_address: str | None = Depends(get_client_ip),
    auth_service: AuthService = Depends(Provide[DependencyContainer.auth_service]),
) -> TokenResponse:
    try:
        user = await auth_service.register_user(
            display_name=body.display_name,
            email=body.email,
            password=body.password,
            ip_address=ip_address,
        )
    except UserAlreadyExistsError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='User with this email already exists',
        ) from error
    return TokenResponse(access_token=create_access_token(user_id=user.id))


@router.post('/login')
@inject
async def login(
    body: LoginRequest,
    ip_address: str | None = Depends(get_client_ip),
    auth_service: AuthService = Depends(Provide[DependencyContainer.auth_service]),
) -> TokenResponse:
    try:
        user = await auth_service.authenticate_user(
            email=body.email,
            password=body.password,
            ip_address=ip_address,
        )
    except InvalidCredentialsError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Invalid email or password',
        ) from error
    return TokenResponse(access_token=create_access_token(user_id=user.id))
