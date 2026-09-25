from fastapi import Depends, HTTPException, status

from apps.api.src.routers.auth.dependencies import get_current_user
from packages.user.src.entities import UserEntity
from packages.user.src.enums import UserRole


async def get_current_admin_user(
    current_user: UserEntity = Depends(get_current_user),
) -> UserEntity:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Admin access required')
    return current_user
