from functools import partial
from typing import Awaitable, Callable

from packages.proxy.src.service import ProxyService


async def sweep_proxy_failure_retention(proxy_service: ProxyService, retention_days: int) -> dict:
    """One sweep pass: deletes every `session_generations` row (successes and failures) older
    than `retention_days`. The job keeps its original `PROXY_FAILURE_RETENTION_SWEEP` name — it is
    a value of the `cronjobname` Postgres enum, which can't be renamed cheaply."""

    deleted_count = await proxy_service.sweep_generation_retention(retention_days=retention_days)
    return {'deleted': deleted_count}


def build_proxy_failure_retention_sweep_job(
    proxy_service: ProxyService,
    retention_days: int,
) -> Callable[[], Awaitable[dict]]:
    return partial(sweep_proxy_failure_retention, proxy_service, retention_days)
