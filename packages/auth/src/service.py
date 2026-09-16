from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import DuplicatedObjectError
from packages.auth.src.exceptions import InvalidCredentialsError, UserAlreadyExistsError
from packages.auth.src.security import hash_password, verify_password
from packages.user.src.entities import UserEntity
from packages.user.src.enums import UserRole
from packages.user.src.repository import UserRepository


async def register_user(session: AsyncSession, display_name: str, email: str, password: str) -> UserEntity:
    repository = UserRepository(session=session)

    existing_user = await repository.get_by_email(email=email)
    if existing_user is not None:
        raise UserAlreadyExistsError

    user_entity = UserEntity(
        display_name=display_name,
        email=email,
        hashed_password=hash_password(password=password),
        role=UserRole.CLIENT,
    )
    try:
        return await repository.create(entity=user_entity)
    except DuplicatedObjectError as error:
        raise UserAlreadyExistsError from error


async def authenticate_user(session: AsyncSession, email: str, password: str) -> UserEntity:
    repository = UserRepository(session=session)

    user_entity = await repository.get_by_email(email=email)
    if user_entity is None or not verify_password(password=password, hashed_password=user_entity.hashed_password):
        raise InvalidCredentialsError

    return await repository.update(entity=UserEntity(id=user_entity.id, last_active_at=datetime.now(tz=timezone.utc)))
