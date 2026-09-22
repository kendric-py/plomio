from functools import partial
from typing import Awaitable, Callable

from packages.automation.src.service import AutomationService


async def dispatch_automation_checks(automation_service: AutomationService, batch_size: int) -> dict:
    """One dispatch pass: for every ACTIVE automation whose `next_check_at` is due and that has no
    check already in flight, creates a single-item PRODUCT_PAGE task via `packages.task` and marks
    it as pending on the automation."""

    return await automation_service.dispatch_due_checks(batch_size=batch_size)


def build_automation_dispatch_job(
    automation_service: AutomationService,
    batch_size: int,
) -> Callable[[], Awaitable[dict]]:
    return partial(dispatch_automation_checks, automation_service, batch_size)
