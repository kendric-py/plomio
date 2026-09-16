from datetime import datetime, timezone

from core.exceptions import DuplicatedObjectError
from core.transaction_manager import AsyncTransactionManager
from packages.auth.src.exceptions import InvalidCredentialsError, UserAlreadyExistsError
from packages.auth.src.security import hash_password, verify_password
from packages.user.src.entities import UserEntity
from packages.user.src.enums import UserRole


class AuthService:
    def __init__(self, transaction_manager: AsyncTransactionManager):
        self.transaction_manager = transaction_manager

    async def register_user(self, display_name: str, email: str, password: str) -> UserEntity:
        async with self.transaction_manager(use_user_repository=True) as transaction:
            existing_user = await transaction.user_repository.get_by_email(email=email)
            if existing_user is not None:
                raise UserAlreadyExistsError

            # First user in an empty system becomes ADMIN, so there's always a way to
            # administer the system without a separate bootstrap/seed step. Not race-safe
            # under concurrent registration on an empty table — acceptable for a one-off
            # bootstrap action, not for the ongoing registration flow.
            is_first_user = not await transaction.user_repository.exists()
            role = UserRole.ADMIN if is_first_user else UserRole.CLIENT

            user_entity = UserEntity(
                display_name=display_name,
                email=email,
                hashed_password=hash_password(password=password),
                role=role,
            )
            try:
                created_user = await transaction.user_repository.create(entity=user_entity)
            except DuplicatedObjectError as error:
                raise UserAlreadyExistsError from error
            else:
                await self.transaction_manager.commit()
            return created_user

    async def authenticate_user(self, email: str, password: str) -> UserEntity:
        async with self.transaction_manager(use_user_repository=True) as transaction:
            user_entity = await transaction.user_repository.get_by_email(email=email)
            if user_entity is None or not verify_password(password=password, hashed_password=user_entity.hashed_password):
                raise InvalidCredentialsError

            authenticated_user = await transaction.user_repository.update(
                entity=UserEntity(id=user_entity.id, last_active_at=datetime.now(tz=timezone.utc)),
            )
            await self.transaction_manager.commit()
            return authenticated_user

    async def has_users(self) -> bool:
        async with self.transaction_manager(use_user_repository=True) as transaction:
            return await transaction.user_repository.exists()
