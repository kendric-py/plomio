from sqlalchemy.ext.asyncio import AsyncSession

from core.repository import BaseRepository
from packages.audit_log.src.entities import AuditLogEntity
from packages.audit_log.src.models import AuditLog


class AuditLogRepository(BaseRepository[AuditLog, AuditLogEntity]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=AuditLog, entity_object=AuditLogEntity, session=session)
