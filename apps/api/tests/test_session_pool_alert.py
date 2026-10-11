import asyncio

import pytest

from apps.api.src.jobs.session_pool_alert import sweep_session_pool
from core.enums import Marketplace
from packages.notifications.src.events import ADMIN_ONLY_EVENT_CODES, EVENT_SESSIONS_DEPLETED
from packages.notifications.src.formatting import build_message_text
from packages.notifications.src.service import NotificationService


class FakeStore:
    def __init__(self, live: dict[Marketplace, int]) -> None:
        self.live = live
        self.marked: set[Marketplace] = set()

    async def live_count(self, marketplace):
        return self.live[marketplace]

    async def mark_depleted(self, marketplace):
        if marketplace in self.marked:
            return False
        self.marked.add(marketplace)
        return True

    async def clear_depleted(self, marketplace):
        self.marked.discard(marketplace)


class FakeNotifications:
    def __init__(self, fail: bool = False) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.fail = fail

    async def notify_admins(self, event_code, payload):
        if self.fail:
            raise RuntimeError('boom')
        self.calls.append((event_code, payload))
        return 1


def _run(coroutine):
    return asyncio.run(coroutine)


def _all(count: int) -> dict[Marketplace, int]:
    return {marketplace: count for marketplace in Marketplace}


def test_alert_fires_once_per_outage_and_rearms_after_recovery() -> None:
    store, notifications = FakeStore(_all(0)), FakeNotifications()

    first = _run(sweep_session_pool(store, notifications))
    second = _run(sweep_session_pool(store, notifications))
    assert sorted(first['alerted']) == sorted(m.value for m in Marketplace)
    assert second['alerted'] == []
    assert len(notifications.calls) == len(Marketplace)

    store.live = _all(3)
    _run(sweep_session_pool(store, notifications))
    assert store.marked == set()

    store.live = _all(0)
    again = _run(sweep_session_pool(store, notifications))
    assert len(again['alerted']) == len(Marketplace)


def test_only_empty_marketplace_is_reported() -> None:
    live = _all(5)
    live[Marketplace.OZON] = 0
    notifications = FakeNotifications()

    result = _run(sweep_session_pool(FakeStore(live), notifications))

    assert result['alerted'] == [Marketplace.OZON.value]
    assert notifications.calls == [(EVENT_SESSIONS_DEPLETED, {'marketplace': 'ozon'})]


def test_failed_notify_clears_mark_so_next_pass_retries() -> None:
    store = FakeStore(_all(0))

    with pytest.raises(RuntimeError):
        _run(sweep_session_pool(store, FakeNotifications(fail=True)))

    assert store.marked == set()


def test_event_is_admin_only_and_has_message() -> None:
    assert EVENT_SESSIONS_DEPLETED in ADMIN_ONLY_EVENT_CODES
    text = build_message_text(
        event_code=EVENT_SESSIONS_DEPLETED, payload={'marketplace': 'ozon'},
    )
    assert 'ozon' in text and 'сессий' in text


def test_list_events_hides_admin_only_from_clients() -> None:
    class Event:
        def __init__(self, code):
            self.event_code = code

    class Repo:
        async def list_active(self):
            return [Event('task.completed'), Event(EVENT_SESSIONS_DEPLETED)]

    class Transaction:
        notification_event_repository = Repo()

    class Manager:
        def __call__(self, **kwargs):
            return self

        async def __aenter__(self):
            return Transaction()

        async def __aexit__(self, *args):
            return None

    service = NotificationService(transaction_manager=Manager())

    client_codes = [e.event_code for e in _run(service.list_events(is_admin=False))]
    admin_codes = [e.event_code for e in _run(service.list_events(is_admin=True))]
    assert client_codes == ['task.completed']
    assert admin_codes == ['task.completed', EVENT_SESSIONS_DEPLETED]
