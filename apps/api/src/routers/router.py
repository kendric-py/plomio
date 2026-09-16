from fastapi import APIRouter

from apps.api.src.routers.auth.endpoints import router as auth_router
from apps.api.src.routers.user.endpoints import router as user_router

api_router = APIRouter(prefix='/api')
api_router.include_router(router=auth_router)
api_router.include_router(router=user_router)
