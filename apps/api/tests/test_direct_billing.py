import asyncio

import pytest
from fastapi import HTTPException

from apps.api.src.routers.direct import dependencies
from apps.api.src.routers.direct.errors import INSUFFICIENT_CREDITS_DETAIL, UNAVAILABLE_DETAIL
from core.enums import Marketplace
from packages.billing.src.enums import ReferenceType
from packages.direct.src.entities import DirectRequest
from packages.direct.src.enums import DirectRequestType


class FakeUser:
    id = 1


class FakeBillingService:
    def __init__(self, balance_positive=True, fail=False):
        self.balance_positive = balance_positive
        self.fail = fail
        self.charges = []

    async def has_positive_balance(self, user_id):
        if self.fail:
            raise RuntimeError('db down')
        return self.balance_positive

    async def charge(self, **kwargs):
        if self.fail:
            raise RuntimeError('db down')
        self.charges.append(kwargs)


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
    asyncio.run(dependencies.require_positive_balance(FakeBillingService(), FakeUser()))


def test_ensure_balance_rejects_with_402():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(dependencies.require_positive_balance(
            FakeBillingService(balance_positive=False), FakeUser(),
        ))
    assert (exc.value.status_code, exc.value.detail) == (402, INSUFFICIENT_CREDITS_DETAIL)


def test_ensure_balance_failure_is_503():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(dependencies.require_positive_balance(
            FakeBillingService(fail=True), FakeUser(),
        ))
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
    }]


def test_charge_failure_is_503():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(dependencies.charge_direct_request(
            FakeBillingService(fail=True), 1, _request(), quantity=1,
        ))
    assert (exc.value.status_code, exc.value.detail) == (503, UNAVAILABLE_DETAIL)

