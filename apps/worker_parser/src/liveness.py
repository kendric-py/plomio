import asyncio
import logging

import aiohttp

from apps.worker_parser.src.config import config
from apps.worker_parser.src.enums import WorkerParserStatus

logger = logging.getLogger(__name__)


class LivenessReporter:
    """Process-level HTTP heartbeat: reports that this worker process is alive, independent of
    whether it currently has a claimed task. Separate from the per-task lease heartbeat
    (TaskService.heartbeat, Postgres-backed) — see apps/worker_parser/AGENTS.md for the open
    questions around the receiving endpoint (address, full request body, behavior on missed
    heartbeats), which are not resolved by this client."""

    def __init__(self) -> None:
        self._status = WorkerParserStatus.READY

    def set_status(self, status: WorkerParserStatus) -> None:
        self._status = status

    async def _send_once(self) -> None:
        if not config.LIVENESS.ENDPOINT_URL:
            return
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    config.LIVENESS.ENDPOINT_URL,
                    json={'worker_name': config.LIVENESS.WORKER_NAME, 'status': self._status.value},
                    timeout=aiohttp.ClientTimeout(total=config.LIVENESS.REQUEST_TIMEOUT_SECONDS),
                ) as response:
                    if response.status != 200:
                        logger.warning('[liveness] unexpected status %d', response.status)
        except Exception as exc:
            logger.warning('[liveness] failed to send heartbeat: %s', exc)

    async def run(self) -> None:
        while True:
            await self._send_once()
            await asyncio.sleep(config.LIVENESS.INTERVAL_SECONDS)
