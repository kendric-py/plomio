from fastapi import APIRouter

from apps.api.src.routers.audit_log.endpoints import admin_router as audit_log_admin_router
from apps.api.src.routers.auth.endpoints import router as auth_router
from apps.api.src.routers.automation.endpoints import router as automation_router
from apps.api.src.routers.billing.endpoints import admin_router as billing_admin_router
from apps.api.src.routers.billing.endpoints import router as billing_router
from apps.api.src.routers.direct.endpoints import router as direct_router
from apps.api.src.routers.notifications.endpoints import router as notifications_router
from apps.api.src.routers.sessions.endpoints import router as sessions_router
from apps.api.src.routers.task.endpoints import router as task_router
from apps.api.src.routers.user.endpoints import admin_router as user_admin_router
from apps.api.src.routers.user.endpoints import router as user_router
from apps.api.src.routers.worker_health.endpoints import router as worker_health_router

api_router = APIRouter(prefix='/api')
api_router.include_router(router=auth_router)
api_router.include_router(router=user_router)
api_router.include_router(router=user_admin_router)
api_router.include_router(router=audit_log_admin_router)
api_router.include_router(router=task_router)
api_router.include_router(router=worker_health_router)
api_router.include_router(router=sessions_router)
api_router.include_router(router=automation_router)
api_router.include_router(router=billing_router)
api_router.include_router(router=billing_admin_router)
api_router.include_router(router=notifications_router)
api_router.include_router(router=direct_router)
