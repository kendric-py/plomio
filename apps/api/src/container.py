from dependency_injector import providers
from dependency_injector.containers import DeclarativeContainer

from apps.api.src.config import config
from core.database import get_database_connection
from core.transaction_manager import AsyncTransactionManager
from packages.auth.src.service import AuthService
from packages.cron.src.service import CronJobService
from packages.result.src.service import ResultService
from packages.task.src.service import TaskService
from packages.user.src.service import UserService
from packages.worker_health.src.redis_store import WorkerHeartbeatStore
from packages.worker_health.src.service import WorkerHealthService

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

    result_service = providers.Factory(
        ResultService,
        transaction_manager=transaction_manager,
    )

    worker_heartbeat_store = providers.Singleton(
        WorkerHeartbeatStore,
        host=config.REDIS.HOST,
        port=config.REDIS.PORT,
        db=config.REDIS.DB,
        password=config.REDIS.PASSWORD,
    )

    worker_health_service = providers.Factory(
        WorkerHealthService,
        transaction_manager=transaction_manager,
    )

    cron_job_service = providers.Factory(
        CronJobService,
        transaction_manager=transaction_manager,
    )
