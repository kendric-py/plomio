from functools import partial
from typing import Awaitable, Callable

from packages.automation.src.service import AutomationService


async def sweep_automation_results(automation_service: AutomationService, batch_size: int) -> dict:
    """One sweep pass: for every automation with a pending check task, if that task reached a
    terminal status, compares the parsed prices against the automation's baseline, writes any
    change to `automation_history`, and clears the pending task."""

    return await automation_service.process_pending_results(batch_size=batch_size)


def build_automation_result_sweep_job(
    automation_service: AutomationService,
    batch_size: int,
) -> Callable[[], Awaitable[dict]]:
    return partial(sweep_automation_results, automation_service, batch_size)
