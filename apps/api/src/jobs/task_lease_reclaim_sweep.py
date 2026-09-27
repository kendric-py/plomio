from functools import partial
from typing import Awaitable, Callable

from packages.task.src.service import TaskService


async def sweep_task_lease_reclaim(task_service: TaskService) -> dict:
    """One sweep pass: move every RUNNING task whose lease (`lease_expires_at`) is in the past
    back to QUEUED — a worker that crashed or lost its heartbeat mid-processing otherwise leaves
    the task stuck in RUNNING forever, which (for an automation's check task) also blocks that
    automation's `pending_task_id` from ever clearing (see packages/automation/AGENTS.md)."""

    reclaimed_count = await task_service.reclaim_expired_leases()
    return {'reclaimed': reclaimed_count}


def build_task_lease_reclaim_sweep_job(task_service: TaskService) -> Callable[[], Awaitable[dict]]:
    return partial(sweep_task_lease_reclaim, task_service)
