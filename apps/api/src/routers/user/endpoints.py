from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Query, status

from apps.api.src.container import DependencyContainer
from apps.api.src.routers.auth.dependencies import get_client_ip, get_current_user
from apps.api.src.routers.billing.dependencies import get_current_admin_user
from apps.api.src.routers.schema import PaginationMeta
from apps.api.src.routers.user.schema import (
    CreateUserRequest,
    UpdateUserRequest,
    UserListResponse,
    UserResponse,
)
from core.exceptions import DuplicatedObjectError, ObjectNotFoundError
from packages.auth.src.exceptions import UserAlreadyExistsError
from packages.auth.src.service import AuthService
from packages.user.src.entities import UserEntity
from packages.user.src.service import UserService

router = APIRouter(prefix="/user", tags=["user"])
admin_router = APIRouter(prefix='/admin/users', tags=['User Admin'])


@router.get('/me')
async def get_me(current_user: UserEntity = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(obj=current_user, from_attributes=True)


@admin_router.get('/')
@inject
async def list_users(
    limit: int = Query(default=100, ge=1, le=500, description='Размер страницы'),
    offset: int = Query(default=0, ge=0, description='Смещение страницы'),
    _current_admin: UserEntity = Depends(get_current_admin_user),
    user_service: UserService = Depends(Provide[DependencyContainer.user_service]),
) -> UserListResponse:
    users, total = await user_service.list_page(limit=limit, offset=offset)
    return UserListResponse(
        items=[UserResponse.model_validate(obj=user, from_attributes=True) for user in users],
        meta=PaginationMeta(total=total, limit=limit, offset=offset),
    )


@admin_router.post('/', status_code=status.HTTP_201_CREATED)
@inject
async def create_user(
    body: CreateUserRequest,
    ip_address: str | None = Depends(get_client_ip),
    current_admin: UserEntity = Depends(get_current_admin_user),
    auth_service: AuthService = Depends(Provide[DependencyContainer.auth_service]),
) -> UserResponse:
    try:
        user = await auth_service.register_user(
            display_name=body.display_name or body.email,
            email=body.email,
            password=body.password,
            ip_address=ip_address,
            role=body.role,
            initial_credits=body.credits,
            granted_by_admin_id=current_admin.id,
        )
    except UserAlreadyExistsError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='User with this email already exists',
        ) from error
    return UserResponse.model_validate(obj=user, from_attributes=True)


@admin_router.delete('/{user_id}', status_code=status.HTTP_204_NO_CONTENT)
@inject
async def delete_user(
    user_id: int,
    current_admin: UserEntity = Depends(get_current_admin_user),
    user_service: UserService = Depends(Provide[DependencyContainer.user_service]),
) -> None:
    if user_id == current_admin.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail='Admin cannot delete themselves',
        )
    try:
        await user_service.delete(user_id=user_id)
    except ObjectNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='User not found') from error


@admin_router.patch('/{user_id}')
@inject
async def update_user(
    user_id: int,
    body: UpdateUserRequest,
    _current_admin: UserEntity = Depends(get_current_admin_user),
    user_service: UserService = Depends(Provide[DependencyContainer.user_service]),
) -> UserResponse:
    try:
        user = await user_service.update_profile(user_id=user_id, **body.model_dump())
    except ObjectNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='User not found') from error
    except DuplicatedObjectError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail='Email already in use',
        ) from error
    return UserResponse.model_validate(obj=user, from_attributes=True)
