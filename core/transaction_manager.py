import asyncio
from types import TracebackType
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from packages.audit_log.src.repository import AuditLogRepository
from packages.result.src.repository import ResultItemRepository
from packages.task.src.repository import TaskItemRepository, TaskRepository
from packages.user.src.repository import UserRepository

REPOSITORIES = {
    'use_user_repository': ('user_repository', UserRepository),
    'use_audit_log_repository': ('audit_log_repository', AuditLogRepository),
    'use_task_repository': ('task_repository', TaskRepository),
    'use_task_item_repository': ('task_item_repository', TaskItemRepository),
    'use_result_repository': ('result_repository', ResultItemRepository),
}


class AsyncTransactionManager:
    user_repository: UserRepository
    audit_log_repository: AuditLogRepository
    task_repository: TaskRepository
    task_item_repository: TaskItemRepository
    result_repository: ResultItemRepository

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory
        self.session: Optional[AsyncSession] = None
        self.use_user_repository = False
        self.use_audit_log_repository = False
        self.use_task_repository = False
        self.use_task_item_repository = False
        self.use_result_repository = False

    def __call__(
        self,
        use_user_repository: bool = False,
        use_audit_log_repository: bool = False,
        use_task_repository: bool = False,
        use_task_item_repository: bool = False,
        use_result_repository: bool = False,
    ) -> 'AsyncTransactionManager':
        self.use_user_repository = use_user_repository
        self.use_audit_log_repository = use_audit_log_repository
        self.use_task_repository = use_task_repository
        self.use_task_item_repository = use_task_item_repository
        self.use_result_repository = use_result_repository
        return self

    def _init_repositories(self, session: AsyncSession) -> None:
        for flag, (attribute_name, repository) in REPOSITORIES.items():
            if not getattr(self, flag):
                continue
            setattr(self, attribute_name, repository(session=session))

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()

    async def flush(self) -> None:
        await self.session.flush()

    async def __aenter__(self) -> 'AsyncTransactionManager':
        self.session = self.session_factory()
        self._init_repositories(session=self.session)
        return self

    async def __aexit__(
        self,
        exception_type: Optional[type[BaseException]],
        exception_value: Optional[BaseException],
        exception_traceback: Optional[TracebackType],
    ) -> None:
        if exception_type:
            await asyncio.shield(self.session.close())
            return None
        await self.session.commit()
        await self.session.close()
        return None
