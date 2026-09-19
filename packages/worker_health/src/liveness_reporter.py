import asyncio
import logging

import aiohttp

from core.configs import LivenessConfig

logger = logging.getLogger(__name__)


class LivenessReporter:
    """Process-level HTTP heartbeat: reports that this worker process is alive, independent of
    whatever it's currently doing. Shared by every worker app (previously two independently
    hand-synced copies, one per app — see packages/worker_health/AGENTS.md).

    `status` is a plain string, not one of the per-app status enums (`WorkerParserStatus`,
    `WorkerSessionsStatus`) — this class has no business knowing about those, and apps don't
    import each other's enums. Callers pass `SomeStatus.X.value`."""

    def __init__(self, config: LivenessConfig, initial_status: str = 'READY') -> None:
        self._config = config
        self._status = initial_status

    def set_status(self, status: str) -> None:
        self._status = status

    async def _send_once(self) -> None:
        if not self._config.ENDPOINT_URL:
            return
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self._config.ENDPOINT_URL,
                    json={'worker_name': self._config.WORKER_NAME, 'status': self._status},
                    timeout=aiohttp.ClientTimeout(total=self._config.REQUEST_TIMEOUT_SECONDS),
                ) as response:
                    if response.status != 200:
                        logger.warning('[liveness] unexpected status %d', response.status)
        except Exception as exc:
            logger.warning('[liveness] failed to send heartbeat: %s', exc)

    async def run(self) -> None:
        while True:
            await self._send_once()
            await asyncio.sleep(self._config.INTERVAL_SECONDS)
