import secrets

from fastapi import Header, HTTPException, status

from apps.api.src.config import config


async def verify_worker_token(
    x_worker_token: str | None = Header(default=None, alias='X-Worker-Token'),
) -> None:
    """Авторизация воркеров на `GET /api/proxy/issue` общим секретом `PROXY_WORKER_TOKEN`.
    Пустой токен в конфиге — выдача выключена (503), а не открыта всем."""
    expected_token = config.PROXY.WORKER_TOKEN
    if not expected_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail='Proxy issuing is not configured',
        )
    if x_worker_token is None or not secrets.compare_digest(
        x_worker_token.encode(), expected_token.encode(),
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Invalid worker token',
        )
