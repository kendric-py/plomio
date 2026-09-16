from typing import Optional

from core.exceptions import ObjectNotFoundError
from core.transaction_manager import AsyncTransactionManager
from packages.user.src.entities import UserEntity


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
