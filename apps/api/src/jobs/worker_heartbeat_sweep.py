import time
from datetime import datetime, timezone
from functools import partial
from typing import Awaitable, Callable

from apps.api.src.config import config
from packages.worker_health.src.redis_store import WorkerHeartbeatStore, parse_member
from packages.worker_health.src.service import WorkerHealthService


async def sweep_worker_heartbeats(
    store: WorkerHeartbeatStore,
    health_service: WorkerHealthService,
) -> dict:
    """One sweep pass: for every worker with a heartbeat in Redis, check whether it's stale, and
    write a MISSED/RECOVERED log entry only on an actual state transition (see
    `WorkerHeartbeatStore.try_claim_missed`/`try_claim_recovered`)."""

    now = time.time()
    last_seen_map = await store.get_last_seen_map()
    missed = recovered = 0

    for member, last_seen in last_seen_map.items():
        worker_type, worker_name = parse_member(member)
        last_seen_at = datetime.fromtimestamp(last_seen, tz=timezone.utc)
        is_stale = (now - last_seen) > config.WORKER_HEALTH.MISSED_THRESHOLD_SECONDS

        if is_stale and await store.try_claim_missed(member):
            await health_service.record_missed(
                worker_type=worker_type,
                worker_name=worker_name,
                last_seen_at=last_seen_at,
                details={'gap_seconds': now - last_seen},
            )
            missed += 1
        elif not is_stale and await store.try_claim_recovered(member):
            await health_service.record_recovered(
                worker_type=worker_type,
                worker_name=worker_name,
                last_seen_at=last_seen_at,
            )
            recovered += 1

    return {'checked': len(last_seen_map), 'missed': missed, 'recovered': recovered}


def build_sweep_job(
    store: WorkerHeartbeatStore,
    health_service: WorkerHealthService,
) -> Callable[[], Awaitable[dict]]:
    return partial(sweep_worker_heartbeats, store, health_service)
