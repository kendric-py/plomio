import asyncio

import pytest
from fastapi import HTTPException

from apps.api.src.routers.direct import dependencies
from apps.api.src.routers.direct.errors import INSUFFICIENT_CREDITS_DETAIL, UNAVAILABLE_DETAIL
from core.enums import Marketplace
from packages.billing.src.enums import ReferenceType
from packages.api_keys.src.exceptions import ApiKeyCreditLimitExceededError
from packages.billing.src.exceptions import InsufficientCreditsError, SpendingLimitExceededError
from packages.direct.src.entities import DirectRequest
from packages.direct.src.enums import DirectRequestType


class FakeUser:
    id = 1


class FakeBillingService:
    def __init__(self, balance_positive=True, fail=False, limit_reached=False):
        self.balance_positive = balance_positive
        self.fail = fail
        self.limit_reached = limit_reached
        self.charges = []

    async def ensure_can_spend(self, user_id):
        if self.fail:
            raise RuntimeError('db down')
        if not self.balance_positive:
            raise InsufficientCreditsError
        if self.limit_reached:
            raise SpendingLimitExceededError

    async def charge(self, **kwargs):
        if self.fail:
            raise RuntimeError('db down')
        self.charges.append(kwargs)


class FakeApiKeyService:
    def __init__(self, exhausted=False):
        self.exhausted = exhausted
        self.checked = []

    async def ensure_can_spend(self, api_key_id):
        self.checked.append(api_key_id)
        if self.exhausted:
            raise ApiKeyCreditLimitExceededError


def _require(billing, api_key_service=None, api_key_id=None):
    return dependencies.require_positive_balance(
        billing_service=billing,
        api_key_service=api_key_service or FakeApiKeyService(),
        current_user=FakeUser(),
        api_key_id=api_key_id,
    )


def _request(request_type=DirectRequestType.REVIEWS):
    return DirectRequest(
        request_id='req1',
        request_type=request_type,
        marketplace=Marketplace.WILDBERRIES,
        input_value='1',
        page_cursor=None,
        created_at=0.0,
        deadline_at=1.0,
    )


def test_ensure_balance_passes_with_positive_balance():
    asyncio.run(_require(FakeBillingService()))


def test_ensure_balance_rejects_with_402():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(_require(FakeBillingService(balance_positive=False)))
    assert (exc.value.status_code, exc.value.detail) == (402, INSUFFICIENT_CREDITS_DETAIL)


def test_ensure_balance_rejects_when_spending_limit_reached():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(_require(FakeBillingService(limit_reached=True)))
    assert (exc.value.status_code, exc.value.detail) == (402, 'Spending limit reached')


def test_ensure_balance_failure_is_503():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(_require(FakeBillingService(fail=True)))
    assert (exc.value.status_code, exc.value.detail) == (503, UNAVAILABLE_DETAIL)


def test_charge_uses_per_type_action_and_request_reference():
    billing = FakeBillingService()
    request = _request(DirectRequestType.REVIEWS)
    asyncio.run(dependencies.charge_direct_request(billing, 7, request, quantity=30))
    assert billing.charges == [{
        'user_id': 7,
        'action_code': 'direct.REVIEWS',
        'quantity': 30,
        'reference_type': ReferenceType.DIRECT,
        'reference_id': 'req1',
        'api_key_id': None,
    }]


def test_api_key_limit_blocks_direct_request_with_402():
    api_keys = FakeApiKeyService(exhausted=True)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(_require(FakeBillingService(), api_key_service=api_keys, api_key_id=5))
    assert (exc.value.status_code, exc.value.detail) == (402, 'API key credit limit reached')
    assert api_keys.checked == [5]


def test_jwt_request_does_not_check_api_key():
    api_keys = FakeApiKeyService(exhausted=True)
    asyncio.run(_require(FakeBillingService(), api_key_service=api_keys, api_key_id=None))
    assert api_keys.checked == []


def test_charge_carries_api_key():
    billing = FakeBillingService()
    asyncio.run(
        dependencies.charge_direct_request(billing, 7, _request(), quantity=1, api_key_id=5),
    )
    assert billing.charges[0]['api_key_id'] == 5


def test_charge_failure_is_503():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(dependencies.charge_direct_request(
            FakeBillingService(fail=True), 1, _request(), quantity=1,
        ))
    assert (exc.value.status_code, exc.value.detail) == (503, UNAVAILABLE_DETAIL)
