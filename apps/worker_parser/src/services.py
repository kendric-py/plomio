from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apps.worker_parser.src.config import config
from core.transaction_manager import AsyncTransactionManager
from packages.api_keys.src.service import ApiKeyService
from packages.billing.src.service import BillingService
from packages.notifications.src.service import NotificationService
from packages.result.src.service import ResultService
from packages.task.src.service import TaskService


def build_services(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[TaskService, ResultService]:
    """Fresh `TaskService`/`ResultService`, each backed by its own `AsyncTransactionManager`.

    `AsyncTransactionManager` keeps the active session/repositories as mutable attributes on
    itself (set in `__aenter__`), not per-call-local state — safe to reuse *sequentially*, but
    two coroutines entering the same instance's `async with` block concurrently race on that
    shared state (one can `commit()` while another is still mid-query on the same
    `AsyncSession`), surfacing as `InvalidRequestError`/`IllegalStateChangeError` from
    SQLAlchemy and crashing the whole process. `apps/worker_parser` runs several `Task`s and,
    within a `Task`, several `TaskItem`s concurrently (see AGENTS.md, "Модель конкурентности"),
    so every independently-scheduled coroutine (each claimed task, its heartbeat loop, each
    concurrently processed item) must call this to get its own instances rather than share ones
    handed down by its caller. `apps/api` doesn't need this helper — its DI container already
    hands out a fresh `AsyncTransactionManager` per request (`providers.Factory`)."""

    billing_service = BillingService(
        transaction_manager=AsyncTransactionManager(session_factory=session_factory),
        notification_service=NotificationService(
            transaction_manager=AsyncTransactionManager(session_factory=session_factory),
        ),
        frontend_base_url=config.FRONTEND_BASE_URL,
        low_balance_threshold=config.BILLING_LOW_BALANCE_THRESHOLD,
    )
    return (
        TaskService(
            transaction_manager=AsyncTransactionManager(session_factory=session_factory),
            billing_service=billing_service,
            notification_service=NotificationService(
                transaction_manager=AsyncTransactionManager(session_factory=session_factory),
            ),
            # Лимит/отзыв API-ключа задачи проверяется после каждого списания результатов.
            api_key_service=ApiKeyService(
                transaction_manager=AsyncTransactionManager(session_factory=session_factory),
                billing_service=billing_service,
            ),
            frontend_base_url=config.FRONTEND_BASE_URL,
        ),
        ResultService(transaction_manager=AsyncTransactionManager(session_factory=session_factory)),
    )
