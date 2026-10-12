from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.buckets import bucket_start
from core.entities import TimeBucketCount
from core.enums import BucketUnit, Marketplace
from core.exceptions import DuplicatedObjectError, ObjectNotFoundError
from core.repository import BaseRepository
from packages.proxy.src.entities import (
    OutcomeCount,
    OutcomeDayCount,
    ProxyGenerationRate,
    ProxyEntity,
    SessionGenerationEntity,
)
from packages.proxy.src.enums import ProxyType
from packages.proxy.src.models import Proxy, SessionGeneration
from packages.sessions.src.enums import SessionGenerationOutcome


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

    async def count_active(self) -> tuple[int, int]:
        """`(активные, всего)` прокси."""
        row = (await self.session.execute(
            select(
                func.count().filter(self.model.is_active.is_(True)),
                func.count(),
            ).select_from(self.model),
        )).one()
        return row[0], row[1]

    async def get_random_active(self, proxy_type: ProxyType | None = None) -> ProxyEntity | None:
        statement = select(self.model).where(self.model.is_active.is_(True))
        if proxy_type is not None:
            statement = statement.where(self.model.proxy_type == proxy_type)
        # Пул прокси маленький (десятки/сотни строк) — ORDER BY random() проще и дешевле любой
        # отдельной схемы выбора и даёт равномерное распределение.
        database_object = await self.session.scalar(statement.order_by(func.random()).limit(1))
        return self._to_entity(database_object=database_object) if database_object else None


class SessionGenerationRepository(BaseRepository[SessionGeneration, SessionGenerationEntity]):
    def __init__(self, session: AsyncSession):
        super().__init__(
            model=SessionGeneration, entity_object=SessionGenerationEntity, session=session,
        )

    def _conditions(
        self,
        proxy_id: int | None,
        marketplace: Marketplace | None,
        date_from: datetime | None,
        date_to: datetime | None,
        outcomes: list[SessionGenerationOutcome] | None,
        include_antibot: bool,
    ) -> list[ColumnElement[bool]]:
        conditions: list[ColumnElement[bool]] = []
        if proxy_id is not None:
            conditions.append(self.model.proxy_id == proxy_id)
        if marketplace is not None:
            conditions.append(self.model.marketplace == marketplace)
        if date_from is not None:
            conditions.append(self.model.created_at >= date_from)
        if date_to is not None:
            conditions.append(self.model.created_at <= date_to)
        if outcomes:
            conditions.append(self.model.outcome.in_(outcomes))
        if not include_antibot:
            conditions.append(self.model.outcome != SessionGenerationOutcome.ANTIBOT_INIT)
        return conditions

    async def recent_outcomes(
        self, marketplace: Marketplace, limit: int,
    ) -> list[SessionGenerationOutcome]:
        """Итоги последних `limit` генераций маркетплейса, новые первыми."""
        statement = (
            select(self.model.outcome)
            .where(self.model.marketplace == marketplace)
            .order_by(self.model.created_at.desc(), self.model.id.desc())
            .limit(limit)
        )
        return list(await self.session.scalars(statement))

    async def count_by_outcome(
        self,
        proxy_id: int | None = None,
        marketplace: Marketplace | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        outcomes: list[SessionGenerationOutcome] | None = None,
        include_antibot: bool = True,
    ) -> list[OutcomeCount]:
        statement = (
            select(self.model.outcome, func.count())
            .where(*self._conditions(
                proxy_id=proxy_id, marketplace=marketplace, date_from=date_from,
                date_to=date_to, outcomes=outcomes, include_antibot=include_antibot,
            ))
            .group_by(self.model.outcome)
            .order_by(func.count().desc(), self.model.outcome)
        )
        rows = await self.session.execute(statement)
        return [OutcomeCount(outcome=outcome, count=count) for outcome, count in rows]

    async def count_by_day(
        self,
        proxy_id: int | None = None,
        marketplace: Marketplace | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        outcomes: list[SessionGenerationOutcome] | None = None,
        include_antibot: bool = True,
    ) -> list[OutcomeDayCount]:
        day = func.date(func.timezone('UTC', self.model.created_at)).label('day')
        statement = (
            select(day, self.model.outcome, func.count())
            .where(*self._conditions(
                proxy_id=proxy_id, marketplace=marketplace, date_from=date_from,
                date_to=date_to, outcomes=outcomes, include_antibot=include_antibot,
            ))
            .group_by(day, self.model.outcome)
            .order_by(day, self.model.outcome)
        )
        rows = await self.session.execute(statement)
        return [
            OutcomeDayCount(day=row_day, outcome=outcome, count=count)
            for row_day, outcome, count in rows
        ]

    async def count_by_bucket(
        self,
        date_from: datetime,
        unit: BucketUnit,
        include_antibot: bool = True,
    ) -> list[TimeBucketCount]:
        """Генерации сессий по интервалам `created_at`; ключ — значение итога."""
        bucket = bucket_start(self.model.created_at, unit).label('bucket')
        statement = (
            select(bucket, self.model.outcome, func.count())
            .where(*self._conditions(
                proxy_id=None, marketplace=None, date_from=date_from, date_to=None,
                outcomes=None, include_antibot=include_antibot,
            ))
            .group_by(bucket, self.model.outcome)
            .order_by(bucket)
        )
        rows = await self.session.execute(statement)
        return [
            TimeBucketCount(bucket=row_bucket, key=outcome.value, count=count)
            for row_bucket, outcome, count in rows
        ]

    async def worst_proxies(
        self, date_from: datetime, limit: int, min_total: int,
    ) -> list[ProxyGenerationRate]:
        """Прокси с наименьшей долей успеха за период. Антибот-ошибки исключены (они почти не
        зависят от прокси); прокси с числом генераций меньше `min_total` не показываются —
        иначе одна неудача из одной попытки даёт «0 %»."""
        success = func.count().filter(self.model.outcome == SessionGenerationOutcome.SUCCESS)
        total = func.count()
        statement = (
            select(self.model.proxy_id, success, total)
            .where(
                self.model.proxy_id.is_not(None),
                *self._conditions(
                    proxy_id=None, marketplace=None, date_from=date_from, date_to=None,
                    outcomes=None, include_antibot=False,
                ),
            )
            .group_by(self.model.proxy_id)
            .having(total >= min_total)
            .order_by((success * 1.0 / total).asc(), total.desc())
            .limit(limit)
        )
        rows = await self.session.execute(statement)
        return [
            ProxyGenerationRate(proxy_id=proxy_id, success=success_count, total=total_count)
            for proxy_id, success_count, total_count in rows
        ]

    async def delete_older_than(self, threshold: datetime) -> int:
        result = await self.session.execute(
            delete(self.model).where(self.model.created_at < threshold),
        )
        return result.rowcount or 0
