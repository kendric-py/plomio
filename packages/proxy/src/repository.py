from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import DuplicatedObjectError, ObjectNotFoundError
from core.repository import BaseRepository
from packages.proxy.src.entities import ProxyEntity
from packages.proxy.src.enums import ProxyType
from packages.proxy.src.models import Proxy


class ProxyRepository(BaseRepository[Proxy, ProxyEntity]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=Proxy, entity_object=ProxyEntity, session=session)

    async def list_page(
        self, limit: int, offset: int, is_active: bool | None = None,
    ) -> tuple[list[ProxyEntity], int]:
        conditions = [] if is_active is None else [self.model.is_active == is_active]
        total = await self.session.scalar(
            select(func.count()).select_from(self.model).where(*conditions),
        )
        statement = (
            select(self.model)
            .where(*conditions)
            .order_by(self.model.id)
            .limit(limit)
            .offset(offset)
        )
        database_objects = await self.session.scalars(statement)
        return self._to_entities(database_objects=database_objects), total or 0

    async def update_fields(self, proxy_id: int, values: dict[str, Any]) -> ProxyEntity:
        """В отличие от `BaseRepository.update`, умеет записывать `None` (сбросить логин, пароль
        или заметку) — поэтому принимает уже отфильтрованный по `model_fields_set` dict."""
        database_object = await self.session.get(entity=self.model, ident=proxy_id)
        if database_object is None:
            raise ObjectNotFoundError
        for field_name, value in values.items():
            setattr(database_object, field_name, value)
        try:
            await self.session.flush()
        except IntegrityError as error:
            await self.session.rollback()
            raise DuplicatedObjectError from error
        return self._to_entity(database_object=database_object)

    async def get_random_active(self, proxy_type: ProxyType | None = None) -> ProxyEntity | None:
        statement = select(self.model).where(self.model.is_active.is_(True))
        if proxy_type is not None:
            statement = statement.where(self.model.proxy_type == proxy_type)
        # Пул прокси маленький (десятки/сотни строк) — ORDER BY random() проще и дешевле любой
        # отдельной схемы выбора и даёт равномерное распределение.
        database_object = await self.session.scalar(statement.order_by(func.random()).limit(1))
        return self._to_entity(database_object=database_object) if database_object else None
