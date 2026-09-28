from functools import partial
from typing import Awaitable, Callable

from packages.notifications.src.service import NotificationService


async def sweep_notification_delivery(
    notification_service: NotificationService,
    batch_size: int,
) -> dict:
    """One sweep pass: sends every PENDING `NotificationDelivery` it can claim this tick, marking
    each one SENT or FAILED (see `NotificationService.dispatch_pending`)."""

    return await notification_service.dispatch_pending(batch_size=batch_size)


def build_notification_delivery_sweep_job(
    notification_service: NotificationService,
    batch_size: int,
) -> Callable[[], Awaitable[dict]]:
    return partial(sweep_notification_delivery, notification_service, batch_size)
