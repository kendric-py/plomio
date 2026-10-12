from datetime import datetime

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.buckets import bucket_start
from core.entities import TimeBucketCount
from core.enums import BucketUnit
from core.repository import BaseRepository
from packages.direct.src.entities import (
    DirectRequestFilters,
    DirectRequestRecordEntity,
    DirectSummaryEntity,
)
from packages.direct.src.enums import DirectOutcome
from packages.direct.src.models import DirectRequestRecord


class DirectRequestRepository(BaseRepository[DirectRequestRecord, DirectRequestRecordEntity]):
    def __init__(self, session: AsyncSession):
        super().__init__(
            model=DirectRequestRecord, entity_object=DirectRequestRecordEntity, session=session,
        )

    def _conditions(self, filters: DirectRequestFilters) -> list[ColumnElement[bool]]:
        conditions: list[ColumnElement[bool]] = []
        if filters.user_id is not None:
            conditions.append(self.model.user_id == filters.user_id)
        if filters.marketplace is not None:
            conditions.append(self.model.marketplace == filters.marketplace)
        if filters.request_type is not None:
            conditions.append(self.model.request_type == filters.request_type)
        if filters.outcome is not None:
            conditions.append(self.model.outcome == filters.outcome)
        if filters.proxy_id is not None:
            conditions.append(self.model.proxy_id == filters.proxy_id)
        if filters.search:
            pattern = '%' + filters.search.replace('%', r'\%').replace('_', r'\_') + '%'
            conditions.append(
                self.model.input_value.ilike(pattern, escape='\\')
                | (self.model.request_id == filters.search),
            )
        if filters.date_from is not None:
            conditions.append(self.model.created_at >= filters.date_from)
        if filters.date_to is not None:
            conditions.append(self.model.created_at <= filters.date_to)
        return conditions

    async def list_page(
        self, filters: DirectRequestFilters, limit: int, offset: int,
    ) -> tuple[list[DirectRequestRecordEntity], int]:
        conditions = self._conditions(filters)
        total = await self.session.scalar(
            select(func.count(self.model.id)).where(*conditions),
        )
        statement = (
            select(self.model)
            .where(*conditions)
            .order_by(self.model.created_at.desc(), self.model.id.desc())
            .limit(limit)
            .offset(offset)
        )
        database_objects = await self.session.scalars(statement)
        return self._to_entities(database_objects=database_objects), total or 0

    async def get_summary(self, filters: DirectRequestFilters) -> DirectSummaryEntity:
        """Счётчики по итогам и типам, списанные кредиты и время успешных запросов (среднее и p95)."""
        conditions = self._conditions(filters)
        by_outcome_rows = await self.session.execute(
            select(self.model.outcome, func.count()).where(*conditions).group_by(self.model.outcome),
        )
        by_type_rows = await self.session.execute(
            select(self.model.request_type, func.count())
            .where(*conditions)
            .group_by(self.model.request_type),
        )
        credits_charged = await self.session.scalar(
            select(func.coalesce(func.sum(self.model.credits_charged), 0)).where(*conditions),
        )
        timing = (await self.session.execute(
            select(
                func.coalesce(func.avg(self.model.total_ms), 0),
                func.coalesce(func.percentile_cont(0.95).within_group(self.model.total_ms), 0),
            ).where(*conditions, self.model.outcome == DirectOutcome.OK),
        )).one()
        by_outcome = {outcome: count for outcome, count in by_outcome_rows}
        return DirectSummaryEntity(
            total=sum(by_outcome.values()),
            by_outcome=by_outcome,
            by_type={request_type: count for request_type, count in by_type_rows},
            credits_charged=credits_charged or 0,
            avg_total_ms=round(timing[0]),
            p95_total_ms=round(timing[1]),
        )

    async def count_by_bucket(self, date_from: datetime, unit: BucketUnit) -> list[TimeBucketCount]:
        """Запросы по интервалам `created_at`; ключ — значение итога (`OK`, `TIMEOUT`, ...)."""
        bucket = bucket_start(self.model.created_at, unit).label('bucket')
        statement = (
            select(bucket, self.model.outcome, func.count())
            .where(self.model.created_at >= date_from)
            .group_by(bucket, self.model.outcome)
            .order_by(bucket)
        )
        rows = await self.session.execute(statement)
        return [
            TimeBucketCount(bucket=row_bucket, key=outcome.value, count=count)
            for row_bucket, outcome, count in rows
        ]

