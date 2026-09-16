import abc
from typing import Generic, Sequence, TypeVar

from pydantic import BaseModel, TypeAdapter
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import BaseSQLModel
from core.exceptions import DuplicatedObjectError, ObjectNotFoundError

DataBaseObject = TypeVar('DataBaseObject', bound=BaseSQLModel)
EntityObject = TypeVar('EntityObject', bound=BaseModel)


class BaseRepositoryInterface(abc.ABC, Generic[EntityObject]):
    @abc.abstractmethod
    async def create(self, entity: EntityObject) -> EntityObject:
        ...

    @abc.abstractmethod
    async def get_by_id(self, entity_id: int) -> EntityObject:
        ...

    @abc.abstractmethod
    async def retrieve_all(self) -> list[EntityObject]:
        ...

    @abc.abstractmethod
    async def update(self, entity: EntityObject, exclude: list[str] | None = None) -> EntityObject:
        ...

    @abc.abstractmethod
    async def delete(self, entity_id: int) -> EntityObject:
        ...

    @abc.abstractmethod
    async def retrieve_all_by_filter(self, entity: EntityObject) -> list[EntityObject]:
        ...


class BaseRepository(
    BaseRepositoryInterface[EntityObject],
    Generic[DataBaseObject, EntityObject],
):
    def __init__(self, model: type[DataBaseObject], entity_object: type[EntityObject], session: AsyncSession):
        self.model = model
        self.entity_object = entity_object
        self.session = session

    async def create(self, entity: EntityObject) -> EntityObject:
        database_object = self.model(**entity.model_dump(exclude_none=True, exclude_unset=True))
        self.session.add(database_object)
        try:
            await self.session.flush()
        except IntegrityError as error:
            await self.session.rollback()
            raise DuplicatedObjectError from error
        return self._to_entity(database_object=database_object)

    async def get_by_id(self, entity_id: int) -> EntityObject:
        database_object = await self.session.get(entity=self.model, ident=entity_id)
        if database_object is None:
            raise ObjectNotFoundError
        return self._to_entity(database_object=database_object)

    async def retrieve_all(self) -> list[EntityObject]:
        statement = select(self.model)
        database_objects = await self.session.scalars(statement)
        return self._to_entities(database_objects=database_objects)

    async def update(self, entity: EntityObject, exclude: list[str] | None = None) -> EntityObject:
        statement = select(self.model).where(self.model.id == entity.id)
        database_object = await self.session.scalar(statement)
        if database_object is None:
            raise ObjectNotFoundError

        entity_data = entity.model_dump(
            exclude_unset=True,
            exclude=exclude,
            exclude_defaults=True,
            exclude_none=True,
        )
        for field_name, value in entity_data.items():
            if not hasattr(database_object, field_name):
                continue
            setattr(database_object, field_name, value)
        await self.session.flush()
        return self._to_entity(database_object=database_object)

    async def delete(self, entity_id: int) -> EntityObject:
        database_object = await self.session.get(entity=self.model, ident=entity_id)
        if database_object is None:
            raise ObjectNotFoundError
        await self.session.delete(database_object)
        return self._to_entity(database_object=database_object)

    async def retrieve_all_by_filter(self, entity: EntityObject) -> list[EntityObject]:
        statement = select(self.model).filter_by(**entity.model_dump(exclude_none=True)).order_by(self.model.id)
        database_objects = await self.session.scalars(statement)
        return self._to_entities(database_objects=database_objects)

    def _to_entity(self, database_object: DataBaseObject) -> EntityObject:
        return self.entity_object.model_validate(obj=database_object, from_attributes=True)

    def _to_entities(self, database_objects: Sequence[DataBaseObject]) -> list[EntityObject]:
        type_adapter = TypeAdapter(list[self.entity_object])
        return type_adapter.validate_python(database_objects, from_attributes=True)
