import asyncio
from types import TracebackType
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from packages.audit_log.src.repository import AuditLogRepository
from packages.automation.src.repository import AutomationCheckLogRepository, AutomationRepository
from packages.billing.src.repository import (
    BillingActionRepository,
    CreditTransactionRepository,
    CreditWalletRepository,
    PricingMultiplierRuleRepository,
)
from packages.cron.src.repository import CronJobRunRepository
from packages.notifications.src.repository import (
    NotificationDeliveryRepository,
    NotificationEventRepository,
    NotificationSettingRepository,
)
from packages.result.src.repository import ResultItemRepository
from packages.task.src.repository import TaskItemRepository, TaskRepository
from packages.user.src.repository import UserRepository
from packages.worker_health.src.repository import WorkerHeartbeatLogRepository

REPOSITORIES = {
    'use_user_repository': ('user_repository', UserRepository),
    'use_audit_log_repository': ('audit_log_repository', AuditLogRepository),
    'use_task_repository': ('task_repository', TaskRepository),
    'use_task_item_repository': ('task_item_repository', TaskItemRepository),
    'use_result_repository': ('result_repository', ResultItemRepository),
    'use_worker_heartbeat_log_repository': (
        'worker_heartbeat_log_repository', WorkerHeartbeatLogRepository,
    ),
    'use_cron_job_run_repository': ('cron_job_run_repository', CronJobRunRepository),
    'use_automation_repository': ('automation_repository', AutomationRepository),
    'use_automation_check_log_repository': (
        'automation_check_log_repository', AutomationCheckLogRepository,
    ),
    'use_billing_action_repository': ('billing_action_repository', BillingActionRepository),
    'use_pricing_multiplier_rule_repository': (
        'pricing_multiplier_rule_repository', PricingMultiplierRuleRepository,
    ),
    'use_credit_wallet_repository': ('credit_wallet_repository', CreditWalletRepository),
    'use_credit_transaction_repository': (
        'credit_transaction_repository', CreditTransactionRepository,
    ),
    'use_notification_event_repository': (
        'notification_event_repository', NotificationEventRepository,
    ),
    'use_notification_setting_repository': (
        'notification_setting_repository', NotificationSettingRepository,
    ),
    'use_notification_delivery_repository': (
        'notification_delivery_repository', NotificationDeliveryRepository,
    ),
}


class AsyncTransactionManager:
    user_repository: UserRepository
    audit_log_repository: AuditLogRepository
    task_repository: TaskRepository
    task_item_repository: TaskItemRepository
    result_repository: ResultItemRepository
    worker_heartbeat_log_repository: WorkerHeartbeatLogRepository
    cron_job_run_repository: CronJobRunRepository
    automation_repository: AutomationRepository
    automation_check_log_repository: AutomationCheckLogRepository
    billing_action_repository: BillingActionRepository
    pricing_multiplier_rule_repository: PricingMultiplierRuleRepository
    credit_wallet_repository: CreditWalletRepository
    credit_transaction_repository: CreditTransactionRepository
    notification_event_repository: NotificationEventRepository
    notification_setting_repository: NotificationSettingRepository
    notification_delivery_repository: NotificationDeliveryRepository

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory
        self.session: Optional[AsyncSession] = None
        self.use_user_repository = False
        self.use_audit_log_repository = False
        self.use_task_repository = False
        self.use_task_item_repository = False
        self.use_result_repository = False
        self.use_worker_heartbeat_log_repository = False
        self.use_cron_job_run_repository = False
        self.use_automation_repository = False
        self.use_automation_check_log_repository = False
        self.use_billing_action_repository = False
        self.use_pricing_multiplier_rule_repository = False
        self.use_credit_wallet_repository = False
        self.use_credit_transaction_repository = False
        self.use_notification_event_repository = False
        self.use_notification_setting_repository = False
        self.use_notification_delivery_repository = False

    def __call__(
        self,
        use_user_repository: bool = False,
        use_audit_log_repository: bool = False,
        use_task_repository: bool = False,
        use_task_item_repository: bool = False,
        use_result_repository: bool = False,
        use_worker_heartbeat_log_repository: bool = False,
        use_cron_job_run_repository: bool = False,
        use_automation_repository: bool = False,
        use_automation_check_log_repository: bool = False,
        use_billing_action_repository: bool = False,
        use_pricing_multiplier_rule_repository: bool = False,
        use_credit_wallet_repository: bool = False,
        use_credit_transaction_repository: bool = False,
        use_notification_event_repository: bool = False,
        use_notification_setting_repository: bool = False,
        use_notification_delivery_repository: bool = False,
    ) -> 'AsyncTransactionManager':
        self.use_user_repository = use_user_repository
        self.use_audit_log_repository = use_audit_log_repository
        self.use_task_repository = use_task_repository
        self.use_task_item_repository = use_task_item_repository
        self.use_result_repository = use_result_repository
        self.use_worker_heartbeat_log_repository = use_worker_heartbeat_log_repository
        self.use_cron_job_run_repository = use_cron_job_run_repository
        self.use_automation_repository = use_automation_repository
        self.use_automation_check_log_repository = use_automation_check_log_repository
        self.use_billing_action_repository = use_billing_action_repository
        self.use_pricing_multiplier_rule_repository = use_pricing_multiplier_rule_repository
        self.use_credit_wallet_repository = use_credit_wallet_repository
        self.use_credit_transaction_repository = use_credit_transaction_repository
        self.use_notification_event_repository = use_notification_event_repository
        self.use_notification_setting_repository = use_notification_setting_repository
        self.use_notification_delivery_repository = use_notification_delivery_repository
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
        if exception_type is not None and issubclass(exception_type, asyncio.CancelledError):
            # Cancellation landed mid-operation (session state is mid-flight, e.g.
            # `_connection_for_bind()` still "in progress") — any further session call, even
            # `close()`, can raise `IllegalStateChangeError` and *replace* the CancelledError,
            # turning a clean shutdown/cancellation into a fatal, unhandled exception that
            # crashes the whole worker process. Let cancellation propagate untouched; the
            # connection pool reclaims the leaked connection on its own (logged as a harmless
            # SAWarning) instead.
            return None
        if exception_type:
            await asyncio.shield(self.session.close())
            return None
        await self.session.commit()
        await self.session.close()
        return None
