from dependency_injector import providers
from dependency_injector.containers import DeclarativeContainer

from apps.api.src.config import config
from core.database import get_database_connection
from core.transaction_manager import AsyncTransactionManager
from packages.audit_log.src.service import AuditLogService
from packages.auth.src.service import AuthService
from packages.automation.src.service import AutomationService
from packages.billing.src.service import BillingService
from packages.cron.src.service import CronJobService
from packages.direct.src.redis_bus import DirectBus
from packages.notifications.src.service import NotificationService
from packages.notifications.src.telegram_client import build_telegram_notifier
from packages.notifications.src.telegram_link_store import TelegramLinkStore
from packages.proxy.src.service import ProxyService
from packages.result.src.service import ResultService
from packages.sessions.src.redis_store import SessionPoolStore
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

    audit_log_service = providers.Factory(
        AuditLogService,
        transaction_manager=transaction_manager,
    )

    telegram_notifier = providers.Singleton(
        build_telegram_notifier,
        bot_token=config.TELEGRAM.BOT_TOKEN,
        proxy_url=config.TELEGRAM.PROXY_URL,
    )

    telegram_link_store = providers.Singleton(
        TelegramLinkStore,
        redis_config=config.REDIS,
    )

    notification_service = providers.Factory(
        NotificationService,
        transaction_manager=transaction_manager,
        telegram_notifier=telegram_notifier,
        telegram_link_store=telegram_link_store,
    )

    billing_service = providers.Factory(
        BillingService,
        transaction_manager=transaction_manager,
        notification_service=notification_service,
        frontend_base_url=config.REST.FRONTEND_BASE_URL,
        low_balance_threshold=config.BILLING.LOW_BALANCE_THRESHOLD,
    )

    auth_service = providers.Factory(
        AuthService,
        transaction_manager=transaction_manager,
        billing_service=billing_service,
        signup_bonus_credits=config.BILLING.SIGNUP_BONUS_CREDITS,
    )

    task_service = providers.Factory(
        TaskService,
        transaction_manager=transaction_manager,
        billing_service=billing_service,
        notification_service=notification_service,
        frontend_base_url=config.REST.FRONTEND_BASE_URL,
    )

    result_service = providers.Factory(
        ResultService,
        transaction_manager=transaction_manager,
    )

    direct_bus = providers.Singleton(
        DirectBus,
        redis_config=config.REDIS,
    )

    worker_heartbeat_store = providers.Singleton(
        WorkerHeartbeatStore,
        redis_config=config.REDIS,
    )

    worker_health_service = providers.Factory(
        WorkerHealthService,
        transaction_manager=transaction_manager,
    )

    cron_job_service = providers.Factory(
        CronJobService,
        transaction_manager=transaction_manager,
    )

    session_pool_store = providers.Singleton(
        SessionPoolStore,
        redis_config=config.REDIS,
    )

    automation_service = providers.Factory(
        AutomationService,
        transaction_manager=transaction_manager,
        task_service=task_service,
        result_service=result_service,
        billing_service=billing_service,
        notification_service=notification_service,
        frontend_base_url=config.REST.FRONTEND_BASE_URL,
    )

    proxy_service = providers.Factory(
        ProxyService,
        transaction_manager=transaction_manager,
    )
