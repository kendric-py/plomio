from functools import partial
from typing import Awaitable, Callable

from packages.task.src.service import TaskService


async def sweep_task_expiry(task_service: TaskService) -> dict:
    """One sweep pass: move every QUEUED task whose `queue_expires_at` is in the past to
    EXPIRED, so a task nobody claimed in time doesn't sit in the queue forever."""

    expired_count = await task_service.expire_stale_queued()
    return {'expired': expired_count}


def build_task_expiry_sweep_job(task_service: TaskService) -> Callable[[], Awaitable[dict]]:
    return partial(sweep_task_expiry, task_service)
