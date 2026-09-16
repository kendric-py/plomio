from typing import NoReturn
import uvicorn

from apps.api.src.server import configure_rest_server  # noqa
from apps.api.src.config import config


def run_rest_server() -> NoReturn:
    uvicorn.run(
        app='apps.api.src.__main__:configure_rest_server',
        factory=True,
        reload=True,
        host=config.REST.APP_HOST,
        port=config.REST.APP_PORT,
        lifespan='on',
    )


if __name__ == '__main__':
    run_rest_server()