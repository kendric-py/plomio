import asyncio
import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from apps.api.src.routers.billing import endpoints
from apps.api.src.routers.billing.schema import UpdateSpendingLimitsRequest
from packages.billing.src.entities import SpendingLimitEntity
from packages.billing.src.exceptions import InsufficientCreditsError, SpendingLimitExceededError
from packages.billing.src.service import (
    EVENT_BALANCE_DEPLETED,
    EVENT_BALANCE_LOW,
    BillingService,
)


def test_billing_routers_build_openapi_schema() -> None:
    app = FastAPI()
    app.include_router(endpoints.router, prefix='/api')
    app.include_router(endpoints.admin_router, prefix='/api')
    paths = app.openapi()['paths']
    assert '/api/billing/limits' in paths


def test_daily_limit_cannot_exceed_monthly() -> None:
    with pytest.raises(ValidationError):
        UpdateSpendingLimitsRequest(daily_limit=500, monthly_limit=100)
    assert UpdateSpendingLimitsRequest(daily_limit=100, monthly_limit=100).daily_limit == 100
    assert UpdateSpendingLimitsRequest(daily_limit=None, monthly_limit=100).daily_limit is None


def test_spending_limit_error_is_insufficient_credits_with_own_detail() -> None:
    # Существующие обработчики 402 ловят InsufficientCreditsError — подкласс должен под них подходить.
    assert issubclass(SpendingLimitExceededError, InsufficientCreditsError)
    assert InsufficientCreditsError.detail == 'Insufficient credits'
    assert SpendingLimitExceededError.detail == 'Spending limit reached'


class FakeNotifications:
    def __init__(self, fail: bool = False) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.fail = fail

    async def notify(self, user_id: int, event_code: str, payload: dict) -> list:
        if self.fail:
            raise RuntimeError('telegram down')
        self.calls.append((event_code, payload))
        return []


def _service(notifications, threshold: int = 100) -> BillingService:
    return BillingService(
        transaction_manager=None,
        notification_service=notifications,
        frontend_base_url='https://plomio.pro',
        low_balance_threshold=threshold,
    )


def _crossing(service: BillingService, before: int, after: int) -> None:
    asyncio.run(service._notify_balance_crossing(user_id=1, balance_before=before, balance_after=after))


def test_depleted_fires_once_when_balance_drops_to_zero_or_below() -> None:
    notifications = FakeNotifications()
    _crossing(_service(notifications), before=5, after=0)
    assert [code for code, _ in notifications.calls] == [EVENT_BALANCE_DEPLETED]
    assert notifications.calls[0][1]['billing_link'] == 'https://plomio.pro/billing'


def test_no_repeat_notification_when_already_below_zero() -> None:
    notifications = FakeNotifications()
    _crossing(_service(notifications), before=-5, after=-20)
    assert notifications.calls == []


def test_low_balance_fires_when_crossing_threshold_but_still_positive() -> None:
    notifications = FakeNotifications()
    _crossing(_service(notifications, threshold=100), before=120, after=80)
    assert [code for code, _ in notifications.calls] == [EVENT_BALANCE_LOW]
    assert notifications.calls[0][1]['threshold'] == 100


def test_low_balance_does_not_repeat_below_threshold() -> None:
    notifications = FakeNotifications()
    _crossing(_service(notifications, threshold=100), before=80, after=60)
    assert notifications.calls == []


def test_threshold_zero_disables_low_balance_but_not_depleted() -> None:
    notifications = FakeNotifications()
    service = _service(notifications, threshold=0)
    _crossing(service, before=120, after=80)
    assert notifications.calls == []
    _crossing(service, before=10, after=-1)
    assert [code for code, _ in notifications.calls] == [EVENT_BALANCE_DEPLETED]


def test_notification_failure_never_breaks_charge() -> None:
    _crossing(_service(FakeNotifications(fail=True)), before=5, after=0)


def test_no_notification_service_is_a_noop() -> None:
    _crossing(_service(None), before=5, after=0)


class FakeSpendingService(BillingService):
    """BillingService без БД: подменяет источники данных у `get_spending_status`/`_get_block_error`."""

    def __init__(self, balance: int, limit: SpendingLimitEntity | None, today: int, month: int):
        super().__init__(transaction_manager=None)
        self._balance, self._limit, self._today, self._month = balance, limit, today, month

    async def has_positive_balance(self, user_id: int) -> bool:
        return self._balance > 0

    async def get_spending_status(self, user_id: int):
        daily = self._limit.daily_limit if self._limit else None
        monthly = self._limit.monthly_limit if self._limit else None
        from packages.billing.src.entities import SpendingStatusEntity

        return SpendingStatusEntity(
            daily_limit=daily,
            monthly_limit=monthly,
            spent_today=self._today,
            spent_this_month=self._month,
            is_limit_reached=(
                (daily is not None and self._today >= daily)
                or (monthly is not None and self._month >= monthly)
            ),
        )


def _spend_error(service: FakeSpendingService):
    return asyncio.run(service._get_block_error(user_id=1))


def test_block_error_is_insufficient_credits_when_balance_not_positive() -> None:
    error = _spend_error(FakeSpendingService(0, None, 0, 0))
    assert type(error) is InsufficientCreditsError


def test_block_error_is_spending_limit_when_daily_limit_reached() -> None:
    limit = SpendingLimitEntity(user_id=1, daily_limit=50, monthly_limit=None)
    error = _spend_error(FakeSpendingService(1000, limit, today=50, month=50))
    assert type(error) is SpendingLimitExceededError


def test_block_error_is_spending_limit_when_monthly_limit_reached() -> None:
    limit = SpendingLimitEntity(user_id=1, daily_limit=None, monthly_limit=300)
    error = _spend_error(FakeSpendingService(1000, limit, today=1, month=300))
    assert type(error) is SpendingLimitExceededError


def test_no_block_when_under_limits_with_positive_balance() -> None:
    limit = SpendingLimitEntity(user_id=1, daily_limit=50, monthly_limit=300)
    assert _spend_error(FakeSpendingService(1000, limit, today=49, month=299)) is None
    assert _spend_error(FakeSpendingService(1000, None, today=999999, month=999999)) is None

