import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.src.config import config
from apps.api.src.container import DependencyContainer
from apps.api.src.jobs.automation_dispatch import build_automation_dispatch_job
from apps.api.src.jobs.automation_history_retention_sweep import (
    build_automation_history_retention_sweep_job,
)
from apps.api.src.jobs.automation_result_sweep import build_automation_result_sweep_job
from apps.api.src.jobs.task_expiry_sweep import build_task_expiry_sweep_job
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

        task_expiry_job = build_task_expiry_sweep_job(task_service=container.task_service())
        task_expiry_task = asyncio.create_task(
            run_periodic(
                job=CronJobName.TASK_EXPIRY_SWEEP,
                interval_seconds=config.TASK.EXPIRY_SWEEP_INTERVAL_SECONDS,
                func=task_expiry_job,
                cron_job_service=container.cron_job_service(),
            ),
        )

        automation_dispatch_job = build_automation_dispatch_job(
            automation_service=container.automation_service(),
            batch_size=config.AUTOMATION.DISPATCH_BATCH_SIZE,
            out_of_stock_check_frequency_minutes=(
                config.AUTOMATION.OUT_OF_STOCK_CHECK_FREQUENCY_MINUTES
            ),
        )
        automation_dispatch_task = asyncio.create_task(
            run_periodic(
                job=CronJobName.AUTOMATION_DISPATCH,
                interval_seconds=config.AUTOMATION.DISPATCH_INTERVAL_SECONDS,
                func=automation_dispatch_job,
                cron_job_service=container.cron_job_service(),
            ),
        )

        automation_result_sweep_job = build_automation_result_sweep_job(
            automation_service=container.automation_service(),
            batch_size=config.AUTOMATION.DISPATCH_BATCH_SIZE,
        )
        automation_result_sweep_task = asyncio.create_task(
            run_periodic(
                job=CronJobName.AUTOMATION_RESULT_SWEEP,
                interval_seconds=config.AUTOMATION.RESULT_SWEEP_INTERVAL_SECONDS,
                func=automation_result_sweep_job,
                cron_job_service=container.cron_job_service(),
            ),
        )

        automation_history_retention_sweep_job = build_automation_history_retention_sweep_job(
            automation_service=container.automation_service(),
        )
        automation_history_retention_sweep_task = asyncio.create_task(
            run_periodic(
                job=CronJobName.AUTOMATION_HISTORY_RETENTION_SWEEP,
                interval_seconds=config.AUTOMATION.HISTORY_RETENTION_SWEEP_INTERVAL_SECONDS,
                func=automation_history_retention_sweep_job,
                cron_job_service=container.cron_job_service(),
            ),
        )
        yield
        sweep_task.cancel()
        task_expiry_task.cancel()
        automation_dispatch_task.cancel()
        automation_result_sweep_task.cancel()
        automation_history_retention_sweep_task.cancel()
        await asyncio.gather(
            sweep_task,
            task_expiry_task,
            automation_dispatch_task,
            automation_result_sweep_task,
            automation_history_retention_sweep_task,
            return_exceptions=True,
        )

    app = FastAPI(title=config.REST.APP_TITLE, lifespan=lifespan)
    app.container = container
    app.container.wire(
        modules=[
            'apps.api.src.routers.auth.dependencies',
            'apps.api.src.routers.auth.endpoints',
            'apps.api.src.routers.task.endpoints',
            'apps.api.src.routers.worker_health.endpoints',
            'apps.api.src.routers.sessions.endpoints',
            'apps.api.src.routers.automation.endpoints',
        ],
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=['*'],
        allow_methods=['*'],
        allow_headers=['*'],
    )
    app.include_router(router=api_router)
    return app
