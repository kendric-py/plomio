from dependency_injector import providers
from dependency_injector.containers import DeclarativeContainer

from apps.api.src.config import config
from core.database import get_database_connection
from core.transaction_manager import AsyncTransactionManager
from packages.auth.src.service import AuthService
from packages.task.src.service import TaskService
from packages.user.src.service import UserService

_, _session_factory = get_database_connection(config=config)


class DependencyContainer(DeclarativeContainer):
    session_factory = providers.Object(_session_factory)

    transaction_manager = providers.Factory(
        AsyncTransactionManager,
        session_factory=session_factory,
    )

    user_service = providers.Factory(
        UserService,
        transaction_manager=transaction_manager,
    )

    auth_service = providers.Factory(
        AuthService,
        transaction_manager=transaction_manager,
    )

    task_service = providers.Factory(
        TaskService,
        transaction_manager=transaction_manager,
    )
