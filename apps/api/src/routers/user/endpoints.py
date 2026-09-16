from fastapi import APIRouter, Depends

from apps.api.src.routers.auth.dependencies import get_current_user
from apps.api.src.routers.user.schema import UserResponse
from packages.user.src.entities import UserEntity

router = APIRouter(prefix="/user", tags=["user"])


@router.get("/")
async def get_users():
    return {"message": "Hello World"}


@router.get('/me')
async def get_me(current_user: UserEntity = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(obj=current_user, from_attributes=True)
