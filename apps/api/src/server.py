import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from apps.api.src.config import config
from apps.api.src.container import DependencyContainer
from apps.api.src.jobs.worker_heartbeat_sweep import build_sweep_job
from apps.api.src.routers.router import api_router
from packages.cron.src.enums import CronJobName
from packages.cron.src.scheduler import run_periodic


def configure_rest_server() -> FastAPI:
    container = DependencyContainer()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Heartbeat-проверка тикает на event loop приложения (asyncio.sleep в run_periodic), а не
        # отдельным процессом/внешним cron'ом — см. packages/cron/AGENTS.md. Дедуп записи в БД при
        # нескольких репликах apps/api сделан в WorkerHeartbeatStore (атомарный Redis SADD/SREM),
        # поэтому таск безопасно крутить независимо в каждой реплике.
        sweep_job = build_sweep_job(
            store=container.worker_heartbeat_store(),
            health_service=container.worker_health_service(),
        )
        sweep_task = asyncio.create_task(
            run_periodic(
                job=CronJobName.WORKER_HEARTBEAT_SWEEP,
                interval_seconds=config.WORKER_HEALTH.SWEEP_INTERVAL_SECONDS,
                func=sweep_job,
                cron_job_service=container.cron_job_service(),
            ),
        )
        yield
        sweep_task.cancel()
        await asyncio.gather(sweep_task, return_exceptions=True)

    app = FastAPI(title=config.REST.APP_TITLE, lifespan=lifespan)
    app.container = container
    app.container.wire(
        modules=[
            'apps.api.src.routers.auth.dependencies',
            'apps.api.src.routers.auth.endpoints',
            'apps.api.src.routers.task.endpoints',
            'apps.api.src.routers.worker_health.endpoints',
        ],
    )
    app.include_router(router=api_router)
    return app
