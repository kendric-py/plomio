from datetime import datetime, timedelta, timezone

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Query

from apps.api.src.container import DependencyContainer
from apps.api.src.routers.automation_admin.dependencies import get_overdue_grace
from apps.api.src.routers.billing.dependencies import get_current_admin_user
from apps.api.src.routers.overview.dependencies import (
    WINDOWS,
    WORST_PROXIES_LIMIT,
    WORST_PROXIES_MIN_TOTAL,
    build_series,
    build_workers_health,
    percent,
    sum_series,
)
from apps.api.src.routers.overview.enums import OverviewWindow
from apps.api.src.routers.overview.schema import (
    OverviewCredits,
    OverviewDirect,
    OverviewGenerations,
    OverviewNotifications,
    OverviewProxies,
    OverviewResponse,
    OverviewTasks,
    OverviewUsers,
    OverviewWorkers,
    OverviewWorstProxy,
)
from apps.api.src.routers.sessions.dependencies import build_marketplace_pool
from core.enums import Marketplace
from packages.automation.src.service import AutomationService
from packages.direct.src.entities import DirectRequestFilters
from packages.direct.src.enums import DirectOutcome
from packages.direct.src.service import DirectService
from packages.billing.src.service import BillingService
from packages.notifications.src.enums import NotificationDeliveryStatus
from packages.notifications.src.service import NotificationService
from packages.proxy.src.service import ProxyService
from packages.sessions.src.enums import SessionGenerationOutcome
from packages.sessions.src.redis_store import SessionPoolStore
from packages.task.src.enums import TaskStatus
from packages.task.src.service import TaskService
from packages.user.src.entities import UserEntity
from packages.user.src.service import UserService
from packages.worker_health.src.redis_store import WorkerHeartbeatStore

admin_router = APIRouter(prefix='/admin/overview', tags=['Overview Admin'])


@admin_router.get('/')
@inject
async def get_overview(
    window: OverviewWindow = Query(
        default=OverviewWindow.DAY, description='Окно сводки: 1h (по минутам), 24h (по часам), 7d (по дням)',
    ),
    overdue_grace: timedelta = Depends(get_overdue_grace),
    _current_admin: UserEntity = Depends(get_current_admin_user),
    task_service: TaskService = Depends(Provide[DependencyContainer.task_service]),
    proxy_service: ProxyService = Depends(Provide[DependencyContainer.proxy_service]),
    notification_service: NotificationService = Depends(
        Provide[DependencyContainer.notification_service],
    ),
    billing_service: BillingService = Depends(Provide[DependencyContainer.billing_service]),
    automation_service: AutomationService = Depends(
        Provide[DependencyContainer.automation_service],
    ),
    user_service: UserService = Depends(Provide[DependencyContainer.user_service]),
    direct_service: DirectService = Depends(Provide[DependencyContainer.direct_service]),
    session_pool_store: SessionPoolStore = Depends(Provide[DependencyContainer.session_pool_store]),
    heartbeat_store: WorkerHeartbeatStore = Depends(
        Provide[DependencyContainer.worker_heartbeat_store],
    ),
) -> OverviewResponse:
    now = datetime.now(timezone.utc)
    length, unit = WINDOWS[window]
    date_from = now - length

    # Сервисы вызываются последовательно: у каждого своя сессия БД, а запросов немного.
    parser_health, sessions_health = build_workers_health(
        last_seen_members=list(await heartbeat_store.get_last_seen_map()),
        missed_members=set(await heartbeat_store.get_missed_members()),
    )

    task_summary = await task_service.get_summary()
    finished = await task_service.get_finished_series(date_from=date_from, unit=unit)

    generation_points = await proxy_service.get_generation_series(date_from=date_from, unit=unit)
    outcome_keys = [outcome.value for outcome in SessionGenerationOutcome]
    by_outcome = {key: sum_series(generation_points, key) for key in outcome_keys}
    generations_total = sum(by_outcome.values())
    pools = [
        await build_marketplace_pool(
            store=session_pool_store, proxy_service=proxy_service, marketplace=marketplace,
        )
        for marketplace in Marketplace
    ]

    active_proxies, total_proxies = await proxy_service.count_proxies()
    worst_proxies = await proxy_service.get_worst_proxies(
        date_from=date_from, limit=WORST_PROXIES_LIMIT, min_total=WORST_PROXIES_MIN_TOTAL,
    )

    pending_notifications = (await notification_service.get_delivery_counts()).get(
        NotificationDeliveryStatus.PENDING, 0,
    )
    notification_points = await notification_service.get_delivery_series(
        date_from=date_from, unit=unit,
    )

    spending = await billing_service.get_spending_stats(date_from=date_from)
    spending_points = await billing_service.get_spending_series(date_from=date_from, unit=unit)
    zero_balance_users, low_balance_users = await billing_service.count_low_balances()

    automation_summary = await automation_service.get_admin_summary(
        date_from=date_from, overdue_grace=overdue_grace,
    )
    direct_summary = await direct_service.get_summary(
        filters=DirectRequestFilters(date_from=date_from),
    )
    direct_points = await direct_service.get_series(date_from=date_from, unit=unit)
    total_users, new_users, active_users = await user_service.get_activity_counts(since=date_from)

    queued = task_summary['tasks'][TaskStatus.QUEUED.value] + task_summary['automations'][TaskStatus.QUEUED.value]
    running = task_summary['tasks'][TaskStatus.RUNNING.value] + task_summary['automations'][TaskStatus.RUNNING.value]

    return OverviewResponse(
        window=window,
        bucket_unit=unit,
        date_from=date_from,
        generated_at=now,
        workers=OverviewWorkers(parser=parser_health, sessions=sessions_health),
        tasks=OverviewTasks(
            queued=queued,
            running=running,
            succeeded=sum_series(finished, TaskStatus.SUCCEEDED.value),
            failed=sum_series(finished, TaskStatus.FAILED.value),
            expired=sum_series(finished, TaskStatus.EXPIRED.value),
            series=build_series(
                points=finished,
                keys=[
                    TaskStatus.SUCCEEDED.value, TaskStatus.FAILED.value, TaskStatus.EXPIRED.value,
                ],
                date_from=date_from, unit=unit, now=now,
            ),
        ),
        generations=OverviewGenerations(
            total=generations_total,
            success_percent=percent(by_outcome[SessionGenerationOutcome.SUCCESS.value], generations_total),
            by_outcome=by_outcome,
            series=build_series(
                points=generation_points, keys=outcome_keys, date_from=date_from, unit=unit, now=now,
            ),
            pools=pools,
        ),
        proxies=OverviewProxies(
            active=active_proxies,
            total=total_proxies,
            worst=[
                OverviewWorstProxy(
                    proxy_id=proxy.id,
                    host=proxy.host,
                    port=proxy.port,
                    success=rate.success,
                    total=rate.total,
                    success_percent=percent(rate.success, rate.total),
                )
                for proxy, rate in worst_proxies
            ],
        ),
        notifications=OverviewNotifications(
            pending=pending_notifications,
            sent=sum_series(notification_points, NotificationDeliveryStatus.SENT.value),
            failed=sum_series(notification_points, NotificationDeliveryStatus.FAILED.value),
            series=build_series(
                points=notification_points,
                keys=[status.value for status in NotificationDeliveryStatus],
                date_from=date_from, unit=unit, now=now,
            ),
        ),
        credits=OverviewCredits(
            spent=spending.total_spent,
            tasks_spent=spending.tasks_spent,
            automations_spent=spending.automations_spent,
            direct_spent=spending.direct_spent,
            zero_balance_users=zero_balance_users,
            low_balance_users=low_balance_users,
            low_balance_threshold=billing_service.low_balance_threshold,
            series=build_series(
                points=spending_points, keys=['spent'], date_from=date_from, unit=unit, now=now,
            ),
        ),
        automations=automation_summary,
        direct=OverviewDirect(
            total=direct_summary.total,
            success_percent=percent(
                direct_summary.by_outcome.get(DirectOutcome.OK, 0), direct_summary.total,
            ),
            by_outcome={
                outcome.value: direct_summary.by_outcome.get(outcome, 0)
                for outcome in DirectOutcome
            },
            credits_charged=direct_summary.credits_charged,
            avg_total_ms=direct_summary.avg_total_ms,
            p95_total_ms=direct_summary.p95_total_ms,
            series=build_series(
                points=direct_points,
                keys=[outcome.value for outcome in DirectOutcome],
                date_from=date_from, unit=unit, now=now,
            ),
        ),
        users=OverviewUsers(total=total_users, new=new_users, active=active_users),
    )
