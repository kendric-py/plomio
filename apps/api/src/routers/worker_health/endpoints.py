import time
from datetime import datetime, timezone

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from apps.api.src.container import DependencyContainer
from apps.api.src.routers.worker_health.schema import (
    HeartbeatRequest,
    HeartbeatResponse,
    WorkerStatusItem,
    WorkerStatusResponse,
)
from packages.worker_health.src.enums import WorkerType
from packages.worker_health.src.redis_store import WorkerHeartbeatStore, parse_member

router = APIRouter(prefix='/worker-health', tags=['Worker Health'])


@router.post('/parser/heartbeat')
@inject
async def parser_heartbeat(
    body: HeartbeatRequest,
    store: WorkerHeartbeatStore = Depends(Provide[DependencyContainer.worker_heartbeat_store]),
) -> HeartbeatResponse:
    await store.touch(WorkerType.PARSER, body.worker_name, body.status)
    return HeartbeatResponse(accepted=True)


@router.post('/sessions/heartbeat')
@inject
async def sessions_heartbeat(
    body: HeartbeatRequest,
    store: WorkerHeartbeatStore = Depends(Provide[DependencyContainer.worker_heartbeat_store]),
) -> HeartbeatResponse:
    await store.touch(WorkerType.SESSIONS, body.worker_name, body.status)
    return HeartbeatResponse(accepted=True)


@router.get('/workers')
@inject
async def list_worker_statuses(
    store: WorkerHeartbeatStore = Depends(Provide[DependencyContainer.worker_heartbeat_store]),
) -> WorkerStatusResponse:
    now = time.time()
    last_seen_map = await store.get_last_seen_map()
    missed_members = await store.get_missed_members()
    status_map = await store.get_status_map()

    workers = []
    for member, last_seen in last_seen_map.items():
        worker_type, worker_name = parse_member(member)
        workers.append(
            WorkerStatusItem(
                worker_type=worker_type,
                worker_name=worker_name,
                status=status_map.get(member),
                last_seen_at=datetime.fromtimestamp(last_seen, tz=timezone.utc),
                gap_seconds=now - last_seen,
                is_missed=member in missed_members,
            ),
        )
    workers.sort(key=lambda worker: (worker.worker_type.value, worker.worker_name))
    return WorkerStatusResponse(workers=workers)
