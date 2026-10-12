from functools import partial
from typing import Awaitable, Callable

from core.enums import Marketplace
from packages.notifications.src.events import EVENT_SESSIONS_DEPLETED, EVENT_SESSIONS_RESTORED
from packages.notifications.src.service import NotificationService
from packages.proxy.src.service import ProxyService
from packages.sessions.src.errors import format_errors_text, group_generations
from packages.sessions.src.redis_store import SessionPoolStore


async def sweep_session_pool(
    store: SessionPoolStore,
    notification_service: NotificationService,
    proxy_service: ProxyService,
) -> dict:
    """One pass over the pools. When a marketplace has no live sessions, notifies admins once per
    outage (`SessionPoolStore.mark_depleted` is an atomic `SET NX`, so several `apps/api` replicas
    don't double-send) with a breakdown of the last generation errors; as soon as the pool has
    sessions again the mark is cleared and admins get a "sessions are back" notification."""

    alerted: list[str] = []
    restored: list[str] = []
    for marketplace in Marketplace:
        live_count = await store.live_count(marketplace=marketplace)
        if live_count > 0:
            if await store.clear_depleted(marketplace=marketplace):
                try:
                    await notification_service.notify_admins(
                        event_code=EVENT_SESSIONS_RESTORED,
                        payload={'marketplace': marketplace.value, 'live_count': live_count},
                    )
                except Exception:
                    # Вернуть пометку, иначе следующий проход не поймёт, что пул был пуст.
                    await store.mark_depleted(marketplace=marketplace)
                    raise
                restored.append(marketplace.value)
            continue
        if not await store.mark_depleted(marketplace=marketplace):
            continue
        recent_generations = await proxy_service.get_recent_generations(marketplace=marketplace)
        try:
            await notification_service.notify_admins(
                event_code=EVENT_SESSIONS_DEPLETED,
                payload={
                    'marketplace': marketplace.value,
                    'errors_text': format_errors_text(
                        group_generations(outcomes=recent_generations),
                    ),
                },
            )
        except Exception:
            # Без снятия пометки следующий проход не попытался бы отправить алерт снова.
            await store.clear_depleted(marketplace=marketplace)
            raise
        alerted.append(marketplace.value)
    return {'alerted': alerted, 'restored': restored}


def build_session_pool_alert_job(
    store: SessionPoolStore,
    notification_service: NotificationService,
    proxy_service: ProxyService,
) -> Callable[[], Awaitable[dict]]:
    return partial(sweep_session_pool, store, notification_service, proxy_service)
