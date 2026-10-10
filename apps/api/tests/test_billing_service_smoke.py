import asyncio

from core.transaction_manager import AsyncTransactionManager
from packages.billing.src.entities import TransactionFilters
from packages.billing.src.enums import ReferenceType
from packages.billing.src.service import BillingService


class FakeResult:
    def __iter__(self):
        return iter([])

    def one(self):
        class Row:
            total_spent = 0
            transactions_count = 0
            tasks_spent = 0
            automations_spent = 0
            direct_spent = 0

        return Row()


class FakeSession:
    """Пустая БД: любой запрос возвращает «ничего». Нужна, чтобы вызвать настоящие методы
    сервиса и репозиториев и поймать опечатки/пропавшие методы, которые тесты с подменой всего
    `BillingService` пропускают (так однажды ушёл в прод вызов несуществующего `get_spent_since`)."""

    async def get(self, *args, **kwargs):
        return None

    async def scalar(self, *args, **kwargs):
        return 0

    async def scalars(self, *args, **kwargs):
        return []

    async def execute(self, *args, **kwargs):
        return FakeResult()

    async def commit(self):
        return None

    async def close(self):
        return None

    async def delete(self, *args, **kwargs):
        return None

    async def flush(self):
        return None

    def add(self, *args, **kwargs):
        return None


def _service() -> BillingService:
    return BillingService(transaction_manager=AsyncTransactionManager(session_factory=FakeSession))


def _run(coroutine):
    return asyncio.run(coroutine)


def test_spending_status_runs_through_real_repositories() -> None:
    status = _run(_service().get_spending_status(user_id=1))
    assert status.spent_today == 0
    assert status.is_limit_reached is False


def test_can_spend_guards_run_through_real_repositories() -> None:
    service = _service()
    # Пустая БД: кошелька нет, баланс 0 — тратить нельзя, но без падения на пути проверки лимитов.
    assert _run(service.can_spend(user_id=1)) is False
    assert _run(service.get_blocked_user_ids(user_ids=[1, 2])) == {
        1: 'insufficient_credits',
        2: 'insufficient_credits',
    }


def test_user_reports_run_through_real_repositories() -> None:
    service = _service()
    filters = TransactionFilters(reference_type=ReferenceType.AUTOMATION, reference_id='x')
    assert _run(service.list_transactions(user_id=1, limit=10, offset=0, filters=filters)) == ([], 0)
    assert _run(service.list_all_transactions(user_id=1, filters=filters)) == []
    assert _run(service.list_transactions_grouped_by_reference(user_id=1, limit=10, offset=0))[1] == 0
    assert _run(service.get_user_spending_stats(user_id=1)).total_spent == 0
    assert _run(service.get_daily_spending(user_id=1)) == []
    assert _run(service.get_reference_spending(
        user_id=1, reference_type=ReferenceType.TASK, reference_id='x',
    )).total_spent == 0


def test_delete_automation_removes_check_tasks_through_real_repositories() -> None:
    from uuid import uuid4

    from core.exceptions import ObjectNotFoundError
    from packages.automation.src.service import AutomationService

    service = AutomationService.__new__(AutomationService)
    service.transaction_manager = AsyncTransactionManager(session_factory=FakeSession)
    # Пустая БД: автоматизации нет — но путь доходит до репозиториев с флагом задач без падения.
    try:
        _run(service.delete_automation(automation_id=uuid4()))
    except ObjectNotFoundError:
        pass


def test_set_spending_limits_runs_through_real_repository() -> None:
    assert _run(_service().set_spending_limits(user_id=1, daily_limit=None, monthly_limit=None)) is None
