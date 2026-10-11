from functools import partial
from typing import Awaitable, Callable

from core.enums import Marketplace
from packages.notifications.src.events import EVENT_SESSIONS_DEPLETED
from packages.notifications.src.service import NotificationService
from packages.sessions.src.redis_store import SessionPoolStore


async def sweep_session_pool(
    store: SessionPoolStore,
    notification_service: NotificationService,
) -> dict:
    """One pass over the pools: when a marketplace has no live sessions, notifies admins once per
    outage (`SessionPoolStore.mark_depleted` is an atomic `SET NX`, so several `apps/api` replicas
    don't double-send); the mark is cleared as soon as the pool has sessions again."""

    alerted: list[str] = []
    for marketplace in Marketplace:
        if await store.live_count(marketplace=marketplace) > 0:
            await store.clear_depleted(marketplace=marketplace)
            continue
        if not await store.mark_depleted(marketplace=marketplace):
            continue
        try:
            await notification_service.notify_admins(
                event_code=EVENT_SESSIONS_DEPLETED,
                payload={'marketplace': marketplace.value},
            )
        except Exception:
            # Без снятия пометки следующий проход не попытался бы отправить алерт снова.
            await store.clear_depleted(marketplace=marketplace)
            raise
        alerted.append(marketplace.value)
    return {'alerted': alerted}


def build_session_pool_alert_job(
    store: SessionPoolStore,
    notification_service: NotificationService,
) -> Callable[[], Awaitable[dict]]:
    return partial(sweep_session_pool, store, notification_service)
