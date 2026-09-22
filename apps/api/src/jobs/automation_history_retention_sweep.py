from functools import partial
from typing import Awaitable, Callable

from packages.automation.src.service import AutomationService


async def sweep_automation_history_retention(automation_service: AutomationService) -> dict:
    """One sweep pass: deletes every `automation_history` row older than its own automation's
    `history_retention_days`."""

    deleted_count = await automation_service.sweep_history_retention()
    return {'deleted': deleted_count}


def build_automation_history_retention_sweep_job(
    automation_service: AutomationService,
) -> Callable[[], Awaitable[dict]]:
    return partial(sweep_automation_history_retention, automation_service)
