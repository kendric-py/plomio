import pytest

from packages.auth.src.service import AuthService


class FakeBillingService:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.grants: list[dict] = []

    async def grant(self, **kwargs):
        if self.fail:
            raise RuntimeError('billing is down')
        self.grants.append(kwargs)


def _service(billing_service: FakeBillingService, bonus: int) -> AuthService:
    return AuthService(
        transaction_manager=None, billing_service=billing_service, signup_bonus_credits=bonus,
    )


@pytest.mark.asyncio
async def test_bonus_is_granted_without_admin():
    billing = FakeBillingService()
    await _service(billing, bonus=100)._grant_signup_bonus(user_id=7)
    assert billing.grants == [
        {'user_id': 7, 'amount': 100, 'admin_id': None, 'comment': 'signup_bonus'},
    ]


@pytest.mark.asyncio
async def test_zero_bonus_grants_nothing():
    billing = FakeBillingService()
    await _service(billing, bonus=0)._grant_signup_bonus(user_id=7)
    assert billing.grants == []


@pytest.mark.asyncio
async def test_billing_failure_does_not_break_registration():
    await _service(FakeBillingService(fail=True), bonus=100)._grant_signup_bonus(user_id=7)
