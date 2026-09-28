from datetime import timedelta
from functools import partial
from typing import Awaitable, Callable

from packages.task.src.service import TaskService


async def sweep_task_lease_reclaim(task_service: TaskService, requeue_ttl: timedelta) -> dict:
    """One sweep pass: move every RUNNING task whose lease (`lease_expires_at`) is in the past
    back to QUEUED — a worker that crashed or lost its heartbeat mid-processing otherwise leaves
    the task stuck in RUNNING forever, which (for an automation's check task) also blocks that
    automation's `pending_task_id` from ever clearing (see packages/automation/AGENTS.md).
    `requeue_ttl` resets `queue_expires_at` on reclaim, the same reasoning as `resume_task` — see
    `TaskRepository.reclaim_expired_leases`."""

    reclaimed_count = await task_service.reclaim_expired_leases(requeue_ttl=requeue_ttl)
    return {'reclaimed': reclaimed_count}


def build_task_lease_reclaim_sweep_job(
    task_service: TaskService, requeue_ttl: timedelta,
) -> Callable[[], Awaitable[dict]]:
    return partial(sweep_task_lease_reclaim, task_service, requeue_ttl)
