import asyncio

import pytest

from apps.api.src.jobs.session_pool_alert import sweep_session_pool
from core.enums import Marketplace
from packages.notifications.src.events import (
    ADMIN_ONLY_EVENT_CODES,
    EVENT_SESSIONS_DEPLETED,
    EVENT_SESSIONS_RESTORED,
)
from packages.notifications.src.formatting import build_message_text
from packages.notifications.src.service import NotificationService
from packages.sessions.src.errors import SessionErrorKind, format_errors_text, group_errors


class FakeStore:
    def __init__(
        self, live: dict[Marketplace, int], errors: list[SessionErrorKind] | None = None,
    ) -> None:
        self.live = live
        self.errors = errors or []
        self.marked: set[Marketplace] = set()

    async def get_recent_errors(self, marketplace):
        return self.errors

    async def live_count(self, marketplace):
        return self.live[marketplace]

    async def mark_depleted(self, marketplace):
        if marketplace in self.marked:
            return False
        self.marked.add(marketplace)
        return True

    async def clear_depleted(self, marketplace):
        was_marked = marketplace in self.marked
        self.marked.discard(marketplace)
        return was_marked


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
    recovery = _run(sweep_session_pool(store, notifications))
    assert store.marked == set()
    assert sorted(recovery['restored']) == sorted(m.value for m in Marketplace)

    store.live = _all(0)
    again = _run(sweep_session_pool(store, notifications))
    assert len(again['alerted']) == len(Marketplace)


def test_only_empty_marketplace_is_reported() -> None:
    live = _all(5)
    live[Marketplace.OZON] = 0
    notifications = FakeNotifications()

    result = _run(sweep_session_pool(FakeStore(live), notifications))

    assert result['alerted'] == [Marketplace.OZON.value]
    assert notifications.calls == [(EVENT_SESSIONS_DEPLETED, {'marketplace': 'ozon', 'errors_text': ''})]


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


def test_restored_notified_once_and_not_without_prior_outage() -> None:
    store, notifications = FakeStore(_all(4)), FakeNotifications()

    quiet = _run(sweep_session_pool(store, notifications))
    assert quiet == {'alerted': [], 'restored': []}

    store.live = _all(0)
    _run(sweep_session_pool(store, notifications))
    notifications.calls.clear()
    store.live = _all(2)
    _run(sweep_session_pool(store, notifications))
    _run(sweep_session_pool(store, notifications))

    assert len(notifications.calls) == len(Marketplace)
    assert all(code == EVENT_SESSIONS_RESTORED for code, _ in notifications.calls)
    assert notifications.calls[0][1]['live_count'] == 2


def test_failed_restore_notify_brings_mark_back_for_retry() -> None:
    store = FakeStore(_all(0))
    _run(sweep_session_pool(store, FakeNotifications()))
    store.live = _all(1)

    with pytest.raises(RuntimeError):
        _run(sweep_session_pool(store, FakeNotifications(fail=True)))

    assert store.marked == set(Marketplace)


def test_depleted_alert_carries_grouped_errors() -> None:
    errors = [SessionErrorKind.VALIDATION] * 7 + [SessionErrorKind.PROXY_UNAVAILABLE] * 2
    errors += [SessionErrorKind.ANTIBOT_INIT]
    notifications = FakeNotifications()

    _run(sweep_session_pool(FakeStore(_all(0), errors=errors), notifications))

    _, payload = notifications.calls[0]
    assert payload['errors_text'] == (
        'Ошибка валидации — 70 %\nПрокси не доступен — 20 %\nАнтибот при инициализации — 10 %'
    )
    text = build_message_text(event_code=EVENT_SESSIONS_DEPLETED, payload=payload)
    assert 'Ошибка валидации — 70 %' in text


def test_group_errors_orders_by_share_and_handles_empty() -> None:
    assert group_errors([]) == [] and format_errors_text([]) == ''
    shares = group_errors([SessionErrorKind.OTHER, SessionErrorKind.ANTIBOT_INIT] * 2)
    assert [(s.kind, s.percent) for s in shares] == [
        (SessionErrorKind.ANTIBOT_INIT, 50), (SessionErrorKind.OTHER, 50),
    ]


def test_restored_event_is_admin_only_and_has_message() -> None:
    assert EVENT_SESSIONS_RESTORED in ADMIN_ONLY_EVENT_CODES
    text = build_message_text(
        event_code=EVENT_SESSIONS_RESTORED, payload={'marketplace': 'ozon', 'live_count': 3},
    )
    assert 'ozon' in text and 'появились' in text
