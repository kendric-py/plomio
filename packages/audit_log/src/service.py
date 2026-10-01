from core.transaction_manager import AsyncTransactionManager
from packages.audit_log.src.entities import AuditLogEntity, AuditLogFilters


class AuditLogService:
    def __init__(self, transaction_manager: AsyncTransactionManager):
        self.transaction_manager = transaction_manager

    async def record(self, entity: AuditLogEntity) -> AuditLogEntity:
        """Пишет одну audit-запись в собственной транзакции (независимо от бизнес-операции)."""
        async with self.transaction_manager(use_audit_log_repository=True) as transaction:
            created = await transaction.audit_log_repository.create(entity=entity)
            await self.transaction_manager.commit()
            return created

    async def list_page(
        self, filters: AuditLogFilters, limit: int, offset: int,
    ) -> tuple[list[AuditLogEntity], int]:
        """Страница audit-записей по фильтрам (новые сверху) и общее число подходящих записей."""
        async with self.transaction_manager(use_audit_log_repository=True) as transaction:
            items = await transaction.audit_log_repository.get_page(
                filters=filters, limit=limit, offset=offset,
            )
            total = await transaction.audit_log_repository.count_by_filters(filters=filters)
            return items, total
