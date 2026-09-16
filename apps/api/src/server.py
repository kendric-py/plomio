from fastapi import FastAPI

from apps.api.src.config import config
from apps.api.src.routers.user.endpoints import router as user_router


def configure_rest_server() -> FastAPI:
    app = FastAPI(title=config.REST.APP_TITLE)
    app.include_router(router=user_router)
    return app
