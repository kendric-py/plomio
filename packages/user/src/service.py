from typing import Optional

from sqlalchemy.exc import IntegrityError

from core.exceptions import DuplicatedObjectError, ObjectNotFoundError
from core.transaction_manager import AsyncTransactionManager
from packages.user.src.entities import UserEntity
from packages.user.src.enums import UserRole


class UserService:
    def __init__(self, transaction_manager: AsyncTransactionManager):
        self.transaction_manager = transaction_manager

    async def get_by_id(self, user_id: int) -> UserEntity:
        async with self.transaction_manager(use_user_repository=True) as transaction:
            try:
                return await transaction.user_repository.get_by_id(entity_id=user_id)
            except ObjectNotFoundError:
                raise ObjectNotFoundError('User not found')

    async def get_by_email(self, email: str) -> Optional[UserEntity]:
        async with self.transaction_manager(use_user_repository=True) as transaction:
            return await transaction.user_repository.get_by_email(email=email)

    async def retrieve_all(self) -> list[UserEntity]:
        async with self.transaction_manager(use_user_repository=True) as transaction:
            return await transaction.user_repository.retrieve_all()

    async def list_page(self, limit: int, offset: int) -> tuple[list[UserEntity], int]:
        """Страница пользователей (по `id`) и общее количество пользователей."""
        async with self.transaction_manager(use_user_repository=True) as transaction:
            users = await transaction.user_repository.get_page(limit=limit, offset=offset)
            total = await transaction.user_repository.count()
            return users, total

    async def update_profile(
        self,
        user_id: int,
        display_name: Optional[str] = None,
        email: Optional[str] = None,
        role: Optional[UserRole] = None,
        telegram_id: Optional[int] = None,
    ) -> UserEntity:
        """Частичное обновление пользователя: меняются только переданные (не `None`) поля.
        Занятый email → `DuplicatedObjectError`, несуществующий пользователь → `ObjectNotFoundError`."""
        patch = UserEntity(
            id=user_id,
            display_name=display_name,
            email=email,
            role=role,
            telegram_id=telegram_id,
        )
        async with self.transaction_manager(use_user_repository=True) as transaction:
            try:
                return await transaction.user_repository.update(entity=patch)
            except ObjectNotFoundError:
                raise ObjectNotFoundError('User not found')
            except IntegrityError as error:
                raise DuplicatedObjectError from error

    async def update(self, user_entity: UserEntity) -> UserEntity:
        async with self.transaction_manager(use_user_repository=True) as transaction:
            try:
                user_entity = await transaction.user_repository.update(entity=user_entity)
            except ObjectNotFoundError:
                raise ObjectNotFoundError('User not found')
            else:
                await self.transaction_manager.commit()
            return user_entity

    async def delete(self, user_id: int) -> UserEntity:
        async with self.transaction_manager(use_user_repository=True) as transaction:
            try:
                user_entity = await transaction.user_repository.delete(entity_id=user_id)
            except ObjectNotFoundError:
                raise ObjectNotFoundError('User not found')
            else:
                await self.transaction_manager.commit()
            return user_entity
