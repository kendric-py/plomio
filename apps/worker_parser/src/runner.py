import asyncio

from apps.worker_parser.src.config import config
from apps.worker_parser.src.direct_runner import run_direct_main
from apps.worker_parser.src.enums import WorkerMode
from apps.worker_parser.src.task_runner import run_poll_loop
from core.database import get_database_connection
from packages.sessions.src.redis_store import SessionPoolStore
from packages.worker_health.src.liveness_reporter import LivenessReporter


async def run_tasks_main(liveness_reporter: LivenessReporter) -> None:
    _, session_factory = get_database_connection(config=config)
    session_client = SessionPoolStore(redis_config=config.REDIS)

    try:
        await asyncio.gather(
            run_poll_loop(session_factory, session_client, liveness_reporter),
            liveness_reporter.run(),
        )
    finally:
        await session_client.close()


async def run_main() -> None:
    """Режим выбирается `WORKER_MODE`; в режиме direct подключение к Postgres не открывается."""
    liveness_reporter = LivenessReporter(config=config.LIVENESS)
    if config.WORKER_MODE == WorkerMode.DIRECT:
        await run_direct_main(liveness_reporter)
    else:
        await run_tasks_main(liveness_reporter)
