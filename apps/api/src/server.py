from fastapi import FastAPI

from apps.api.src.config import config
from apps.api.src.container import DependencyContainer
from apps.api.src.routers.router import api_router


def configure_rest_server() -> FastAPI:
    app = FastAPI(title=config.REST.APP_TITLE)
    app.container = DependencyContainer()
    app.container.wire(
        modules=[
            'apps.api.src.routers.auth.dependencies',
            'apps.api.src.routers.auth.endpoints',
            'apps.api.src.routers.task.endpoints',
        ],
    )
    app.include_router(router=api_router)
    return app
