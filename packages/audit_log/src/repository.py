from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.repository import BaseRepository
from packages.audit_log.src.entities import AuditLogEntity, AuditLogFilters
from packages.audit_log.src.models import AuditLog


class AuditLogRepository(BaseRepository[AuditLog, AuditLogEntity]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=AuditLog, entity_object=AuditLogEntity, session=session)

    async def get_page(
        self, filters: AuditLogFilters, limit: int, offset: int,
    ) -> list[AuditLogEntity]:
        """Страница записей, новые сверху (`id` — тай-брейк для одинакового `created_at`)."""
        statement = (
            self._apply_filters(statement=select(self.model), filters=filters)
            .order_by(self.model.created_at.desc(), self.model.id.desc())
            .limit(limit)
            .offset(offset)
        )
        database_objects = await self.session.scalars(statement)
        return self._to_entities(database_objects=database_objects)

    async def count_by_filters(self, filters: AuditLogFilters) -> int:
        statement = self._apply_filters(
            statement=select(func.count(self.model.id)), filters=filters,
        )
        return await self.session.scalar(statement)

    def _apply_filters(self, statement: Select, filters: AuditLogFilters) -> Select:
        """Общие фильтры для выборки и `count`, чтобы они не расходились."""
        exact_matches = {
            'user_id': filters.user_id,
            'action': filters.action,
            'action_type': filters.action_type,
            'status': filters.status,
            'error_reason': filters.error_reason,
            'target_type': filters.target_type,
            'target_id': filters.target_id,
            'ip_address': filters.ip_address,
        }
        for column_name, value in exact_matches.items():
            if value is not None:
                statement = statement.where(getattr(self.model, column_name) == value)
        if filters.date_from is not None:
            statement = statement.where(self.model.created_at >= filters.date_from)
        if filters.date_to is not None:
            statement = statement.where(self.model.created_at <= filters.date_to)
        return statement
