from typing import Any

from core.transaction_manager import AsyncTransactionManager
from packages.proxy.src.entities import ProxyEntity
from packages.proxy.src.enums import ProxyType


class ProxyService:
    def __init__(self, transaction_manager: AsyncTransactionManager):
        self.transaction_manager = transaction_manager

    async def list_page(
        self, limit: int, offset: int, is_active: bool | None = None,
    ) -> tuple[list[ProxyEntity], int]:
        async with self.transaction_manager(use_proxy_repository=True) as transaction:
            return await transaction.proxy_repository.list_page(
                limit=limit, offset=offset, is_active=is_active,
            )

    async def create_proxy(
        self,
        proxy_type: ProxyType,
        host: str,
        port: int,
        username: str | None = None,
        password: str | None = None,
        note: str | None = None,
        is_active: bool = True,
    ) -> ProxyEntity:
        """`DuplicatedObjectError`, если прокси с таким (тип, хост, порт, логин) уже есть."""
        async with self.transaction_manager(use_proxy_repository=True) as transaction:
            created_proxy = await transaction.proxy_repository.create(
                entity=ProxyEntity(
                    proxy_type=proxy_type,
                    host=host,
                    port=port,
                    username=username,
                    password=password,
                    note=note,
                    is_active=is_active,
                ),
            )
            await self.transaction_manager.commit()
        return created_proxy

    async def update_proxy(self, proxy_id: int, values: dict[str, Any]) -> ProxyEntity:
        """`values` — только реально переданные поля (`None` допустим: сбрасывает логин/пароль/
        заметку). `ObjectNotFoundError` / `DuplicatedObjectError` пробрасываются вызывающему."""
        async with self.transaction_manager(use_proxy_repository=True) as transaction:
            updated_proxy = await transaction.proxy_repository.update_fields(
                proxy_id=proxy_id, values=values,
            )
            await self.transaction_manager.commit()
        return updated_proxy

    async def delete_proxy(self, proxy_id: int) -> None:
        async with self.transaction_manager(use_proxy_repository=True) as transaction:
            await transaction.proxy_repository.delete(entity_id=proxy_id)
            await self.transaction_manager.commit()

    async def issue_random(self, proxy_type: ProxyType | None = None) -> ProxyEntity | None:
        """Случайный активный прокси (опционально заданного типа); `None`, если таких нет."""
        async with self.transaction_manager(use_proxy_repository=True) as transaction:
            return await transaction.proxy_repository.get_random_active(proxy_type=proxy_type)
