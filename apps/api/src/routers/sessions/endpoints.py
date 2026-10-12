from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from apps.api.src.container import DependencyContainer
from apps.api.src.routers.sessions.dependencies import build_marketplace_pool
from apps.api.src.routers.sessions.schema import SessionPoolResponse
from core.enums import Marketplace
from packages.proxy.src.service import ProxyService
from packages.sessions.src.redis_store import SessionPoolStore

router = APIRouter(prefix='/sessions', tags=['Sessions'])


@router.get('/pool')
@inject
async def get_session_pool(
    store: SessionPoolStore = Depends(Provide[DependencyContainer.session_pool_store]),
    proxy_service: ProxyService = Depends(Provide[DependencyContainer.proxy_service]),
) -> SessionPoolResponse:
    pools = [
        await build_marketplace_pool(
            store=store, proxy_service=proxy_service, marketplace=marketplace,
        )
        for marketplace in Marketplace
    ]
    return SessionPoolResponse(marketplaces=pools)
