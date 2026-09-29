import asyncio
from dataclasses import dataclass, field

import pytest

from apps.worker_parser.src import hot_session
from apps.worker_parser.src.config import config
from apps.worker_parser.src.entities import SessionMessage
from apps.worker_parser.src.exceptions import BrowserInitError
from apps.worker_parser.src.hot_session import HotSessionSlot
from core.enums import Marketplace


class FakeHttp:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


@dataclass
class FakeStore:
    sessions: list[SessionMessage] = field(default_factory=list)
    acquire_kwargs: list[dict] = field(default_factory=list)
    released: list[str] = field(default_factory=list)

    async def acquire_session(self, **kwargs):
        self.acquire_kwargs.append(kwargs)
        return self.sessions.pop(0) if self.sessions else None

    async def release(self, session_message, min_ttl_margin_seconds):
        self.released.append(session_message.session_id)


def make_session() -> SessionMessage:
    return SessionMessage(
        marketplace=Marketplace.OZON, cookies={}, user_agent='ua', sec_ch_ua='',
        sec_ch_ua_platform='',
    )


@pytest.fixture
def http_clients(monkeypatch):
    clients: list[FakeHttp] = []

    def factory(session_message):
        clients.append(FakeHttp())
        return clients[-1]

    monkeypatch.setitem(hot_session.HTTP_SESSION_FACTORY_BY_MARKETPLACE, Marketplace.OZON, factory)
    return clients


def make_slot(store: FakeStore) -> HotSessionSlot:
    return HotSessionSlot(Marketplace.OZON, store)


@pytest.mark.asyncio
async def test_session_is_shared_and_not_returned_between_requests(http_clients):
    store = FakeStore(sessions=[make_session(), make_session()])
    slot = make_slot(store)

    first = await slot.acquire(deadline=None)
    second = await slot.acquire(deadline=None)
    await slot.release(first)
    await slot.release(second)
    third = await slot.acquire(deadline=None)

    assert first is second is third
    assert len(store.acquire_kwargs) == 1
    assert store.released == []
    assert len(http_clients) == 1 and not http_clients[0].closed


@pytest.mark.asyncio
async def test_pool_threshold_is_plain_ttl_margin(http_clients):
    """Ловушка: возраст ротации нельзя добавлять к порогу TTL — TTL сессий 7 минут."""
    store = FakeStore(sessions=[make_session()])
    await make_slot(store).acquire(deadline=None)
    assert store.acquire_kwargs[0]['min_ttl_margin_seconds'] == (
        config.SESSION_POOL.MIN_TTL_MARGIN_SECONDS
    )


@pytest.mark.asyncio
async def test_rotation_by_age_returns_old_session_to_pool_after_last_user(
    http_clients, monkeypatch,
):
    monkeypatch.setattr(config.DIRECT, 'HOT_SESSION_MAX_AGE_SECONDS', 0.0)
    old, new = make_session(), make_session()
    store = FakeStore(sessions=[old, new])
    slot = make_slot(store)

    old_handle = await slot.acquire(deadline=None)
    new_handle = await slot.acquire(deadline=None)

    assert new_handle.session_message is new
    # Старую нельзя закрывать под ногами запроса, который её ещё использует.
    assert store.released == [] and not http_clients[0].closed
    await slot.release(old_handle)
    assert store.released == [old.session_id]
    assert http_clients[0].closed


@pytest.mark.asyncio
async def test_discard_drops_session_without_returning_it_to_pool(http_clients):
    first_session, second_session = make_session(), make_session()
    store = FakeStore(sessions=[first_session, second_session])
    slot = make_slot(store)

    handle = await slot.acquire(deadline=None)
    await slot.discard(handle)
    next_handle = await slot.acquire(deadline=None)

    assert store.released == []
    assert http_clients[0].closed
    assert next_handle.session_message is second_session


@pytest.mark.asyncio
async def test_discard_waits_for_other_users_before_closing(http_clients):
    store = FakeStore(sessions=[make_session()])
    slot = make_slot(store)

    first = await slot.acquire(deadline=None)
    await slot.acquire(deadline=None)
    await slot.discard(first)

    assert not http_clients[0].closed


@pytest.mark.asyncio
async def test_no_session_raises_after_wait(http_clients, monkeypatch):
    monkeypatch.setattr(config.DIRECT, 'SESSION_WAIT_SECONDS', 0.3)
    slot = make_slot(FakeStore())
    with pytest.raises(BrowserInitError):
        await slot.acquire(deadline=None)


@pytest.mark.asyncio
async def test_wait_is_capped_by_remaining_deadline(http_clients, monkeypatch):
    monkeypatch.setattr(config.DIRECT, 'SESSION_WAIT_SECONDS', 10.0)
    slot = make_slot(FakeStore())
    loop = asyncio.get_running_loop()
    started = loop.time()
    with pytest.raises(BrowserInitError):
        await slot.acquire(deadline=asyncio.get_running_loop().time() + 0.3)
    assert loop.time() - started < 2


@pytest.mark.asyncio
async def test_warm_up_takes_session_and_keeps_it(http_clients):
    store = FakeStore(sessions=[make_session()])
    slot = make_slot(store)
    await slot.warm_up()
    handle = await slot.acquire(deadline=None)
    assert len(store.acquire_kwargs) == 1
    assert handle is not None
